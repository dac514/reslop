--[[
  Dev bridge: a tiny TCP server inside the tool's own Lua state so an external
  agent (scripts/renoise.py) can evaluate Lua, inspect dialogs, read the log and
  soft-reload `src/` without touching the Renoise GUI.

  * Loaded only when this file exists (see main.lua); `just package` strips dev/.
  * Binds 127.0.0.1 unless dev/bind says otherwise. When dev/.token exists every
    request must carry it (renoise.py install writes both for WSL setups).
  * Socket callbacks run on Renoise's main thread: never block, never call
    client:receive(), never close sockets here (the client closes).

  Wire format (both directions, binary safe):
    <total_len>\n<records>
    records := (<name> <len>\n<bytes>)*
]]

local commands = require "dev.commands"

local DEFAULT_PORT = 18765
local MAX_REPLY = 1024 * 1024
local SEND_CHUNK = 32 * 1024
local BUFFER_TTL = 30 -- seconds
local BIND_RETRIES = 10
local RING_SIZE = 500

local Bridge = {}

-- Files ----------------------------------------------------------------------

local function bundle_path()
  local p = renoise.tool().bundle_path
  local last = p:sub(-1)
  if last ~= "/" and last ~= "\\" then
    p = p .. "/"
  end
  return p
end

---@param path string
---@return string?
local function read_file(path)
  if not io.exists(path) then
    return nil
  end
  local fh = io.open(path, "rb")
  if not fh then
    return nil
  end
  local data = fh:read "*a"
  fh:close()
  return data
end

---@param path string
---@param data string
local function write_file(path, data)
  local fh = io.open(path, "wb")
  if not fh then
    return false
  end
  fh:write(data)
  fh:close()
  return true
end

---@param s string
---@return string
local function trim(s)
  return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

-- Log ring -------------------------------------------------------------------

---@class BridgeRingEntry
---@field t integer
---@field kind string
---@field text string

---@class BridgeRing
---@field items BridgeRingEntry[]
---@field max integer
local Ring = {}
Ring.__index = Ring

---@param max integer
---@return BridgeRing
function Ring.new(max)
  return setmetatable({ items = {}, max = max }, Ring)
end

---@param kind string
---@param text string
function Ring:push(kind, text)
  self.items[#self.items + 1] = { t = os.time(), kind = kind, text = text }
  if #self.items > self.max then
    table.remove(self.items, 1)
  end
end

---@param n integer
---@return BridgeRingEntry[]
function Ring:tail(n)
  local out = {}
  for i = math.max(1, #self.items - n + 1), #self.items do
    out[#out + 1] = self.items[i]
  end
  return out
end

function Ring:clear()
  self.items = {}
end

-- State ----------------------------------------------------------------------

---@class BridgeState
---@field boot_id string
---@field reload_count integer
---@field port integer?
---@field bind string
---@field token string?
---@field bundle_path string
---@field ring BridgeRing
---@field server renoise.Socket.SocketServer?
---@field buffers table<string, { data: string, t: integer }>
---@field capture_buf string[]?
---@field port_candidates integer[]
---@field attempt integer
---@field retry fun()?
---@field capture fun(fn: function): string, table
---@field install_sink fun()
local state

---@param kind string
---@param text string
local function record(kind, text)
  state.ring:push(kind, text)
  if state.capture_buf then
    state.capture_buf[#state.capture_buf + 1] = text
  end
end

local function pack(...)
  return { n = select("#", ...), ... }
end

---Run `fn` capturing everything printed or logged while it runs.
---@param fn function
---@return string output, table results `{ n, ok, ... }` as returned by xpcall
local function capture(fn)
  local prev = state.capture_buf
  state.capture_buf = {}
  local results = pack(xpcall(fn, function(err)
    return debug.traceback(tostring(err), 2)
  end))
  local out = table.concat(state.capture_buf, "\n")
  state.capture_buf = prev
  return out, results
end

local function install_print_hook()
  local orig = rawget(_G, "__dev_orig_print") or print
  _G.__dev_orig_print = orig
  _G.print = function(...)
    local parts = {}
    for i = 1, select("#", ...) do
      parts[i] = tostring((select(i, ...)))
    end
    record("print", table.concat(parts, "\t"))
    orig(...)
  end
end

local function install_sink()
  if not APP then
    return
  end
  local orig = rawget(_G, "__dev_orig_print") or print
  APP.set_log_sink(function(kind, text)
    record(kind, text)
    orig(("[%s] %s"):format(kind, text))
  end)
end

-- Framing --------------------------------------------------------------------

---@param buf string
---@return table<string, string>? records, string? err
local function parse_frame(buf)
  local nl = buf:find("\n", 1, true)
  if not nl then
    if #buf > 20 then
      return nil, "bad frame header"
    end
    return nil
  end
  local total = tonumber(buf:sub(1, nl - 1))
  if not total then
    return nil, "bad frame header"
  end
  if #buf < nl + total then
    return nil
  end
  local body = buf:sub(nl + 1, nl + total)
  local records, pos = {}, 1
  while pos <= #body do
    local lnl = body:find("\n", pos, true)
    if not lnl then
      return nil, "bad record header"
    end
    local name, len = body:sub(pos, lnl - 1):match "^([%w_]+) (%d+)$"
    if not name then
      return nil, "bad record header"
    end
    len = tonumber(len)
    records[name] = body:sub(lnl + 1, lnl + len)
    pos = lnl + len + 1
  end
  return records
end

---@param records table<string, any>
---@return string
local function encode(records)
  local names = {}
  for k, v in pairs(records) do
    if v ~= nil then
      names[#names + 1] = k
    end
  end
  table.sort(names, function(a, b)
    if a == "status" then
      return true
    elseif b == "status" then
      return false
    end
    return a < b
  end)
  local parts = {}
  for _, k in ipairs(names) do
    local v = tostring(records[k])
    parts[#parts + 1] = ("%s %d\n%s"):format(k, #v, v)
  end
  local body = table.concat(parts)
  return ("%d\n%s"):format(#body, body)
end

---@param client renoise.Socket.SocketClient
---@param data string
---@return boolean ok, string? err
local function send(client, data)
  local pos = 1
  while pos <= #data do
    local ok, err = client:send(data:sub(pos, pos + SEND_CHUNK - 1))
    if not ok then
      return false, err
    end
    pos = pos + SEND_CHUNK
  end
  return true
end

-- Dispatch -------------------------------------------------------------------

---@param records table<string, string>
---@return string reply
function Bridge.dispatch(records)
  local kind = records.kind or "?"
  local handler = commands[kind]
  if not handler then
    return encode { status = "error", error = "unknown request kind: " .. kind }
  end
  local ok, reply = pcall(handler, records, state)
  if not ok then
    record("error", ("handler %s crashed: %s"):format(kind, tostring(reply)))
    return encode { status = "error", error = "bridge handler crashed: " .. tostring(reply) }
  end
  reply.status = reply.status or "ok"
  for k, v in pairs(reply) do
    local text = tostring(v)
    if #text > MAX_REPLY then
      reply[k] = text:sub(1, MAX_REPLY) .. "\n...[truncated]"
      reply.truncated = "1"
    end
  end
  return encode(reply)
end

---@param client renoise.Socket.SocketClient
---@param records table<string, string>
---@return boolean
local function authorized(client, records)
  if state.token then
    return records.token == state.token
  end
  local addr = client.peer_address
  return addr == "127.0.0.1" or addr == "::1" or addr == "localhost"
end

---@param client renoise.Socket.SocketClient
---@return string
local function client_key(client)
  local ok, key = pcall(function()
    return client.peer_address .. ":" .. tostring(client.peer_port)
  end)
  if ok then
    return key
  end
  return tostring(client)
end

local notifier = {}

---@param err string
function notifier.socket_error(err)
  record("bridge", "socket error: " .. tostring(err))
end

function notifier.socket_accepted()
  local now = os.time()
  for key, buf in pairs(state.buffers) do
    if now - buf.t > BUFFER_TTL then
      state.buffers[key] = nil
    end
  end
end

---@param client renoise.Socket.SocketClient
---@param message string
function notifier.socket_message(client, message)
  local key = client_key(client)
  local buf = state.buffers[key]
  if not buf then
    buf = { data = "", t = os.time() }
    state.buffers[key] = buf
  end
  buf.data = buf.data .. message
  local records, err = parse_frame(buf.data)
  if err then
    state.buffers[key] = nil
    send(client, encode { status = "error", error = "protocol: " .. err })
    return
  end
  if not records then
    return -- wait for the rest of the frame
  end
  state.buffers[key] = nil
  if not authorized(client, records) then
    record("bridge", "rejected request from " .. key)
    return
  end
  local ok, serr = send(client, Bridge.dispatch(records))
  if not ok then
    record("bridge", "send failed: " .. tostring(serr))
  end
end

-- Server lifecycle -----------------------------------------------------------

local function try_bind()
  local port = state.port_candidates[state.attempt]
  if not port then
    record("bridge", "giving up: could not bind any port")
    return
  end
  local server, err = renoise.Socket.create_server(state.bind, port, renoise.Socket.PROTOCOL_TCP)
  if server then
    state.server = server
    state.port = port
    server:run(notifier)
    write_file(state.bundle_path .. "dev/.port", ("%d\n%s\n"):format(port, state.boot_id))
    record("bridge", ("listening on %s:%d (boot %s)"):format(state.bind, port, state.boot_id))
    return
  end
  state.attempt = state.attempt + 1
  record("bridge", ("bind %s:%d failed (%s), retrying"):format(state.bind, port, tostring(err)))
  renoise.tool():add_timer(state.retry, 500)
end

---Stop the running bridge (if any). Also the tool_will_unload notifier.
function Bridge.stop()
  local s = rawget(_G, "__dev_bridge")
  if not s then
    return
  end
  local tool = renoise.tool()
  if s.retry and tool:has_timer(s.retry) then
    tool:remove_timer(s.retry)
  end
  if s.server then
    pcall(function()
      s.server:stop()
    end)
    pcall(function()
      s.server:close()
    end)
    s.server = nil
  end
  os.remove(s.bundle_path .. "dev/.port")
end

---Start the bridge. Safe to call again: a previous instance is stopped first.
function Bridge.start()
  Bridge.stop()
  local bp = bundle_path()
  local port = tonumber(trim(read_file(bp .. "dev/port") or "")) or DEFAULT_PORT
  local bind = trim(read_file(bp .. "dev/bind") or "")
  if bind == "" then
    bind = "127.0.0.1"
  end
  ---@type string?
  local token = trim(read_file(bp .. "dev/.token") or "")
  if token == "" then
    token = nil
  end
  local candidates = {}
  for _ = 1, BIND_RETRIES do
    candidates[#candidates + 1] = port
  end
  for i = 1, 9 do
    candidates[#candidates + 1] = port + i
  end
  local clock_digits = (tostring(os.clock()):gsub("%D", ""))
  state = {
    boot_id = ("%d-%s"):format(os.time(), clock_digits),
    reload_count = 0,
    port = nil,
    bind = bind,
    token = token,
    bundle_path = bp,
    ring = Ring.new(RING_SIZE),
    server = nil,
    buffers = {},
    capture_buf = nil,
    port_candidates = candidates,
    attempt = 1,
    retry = nil,
    capture = capture,
    install_sink = install_sink,
  }
  state.retry = function()
    renoise.tool():remove_timer(state.retry)
    try_bind()
  end
  _G.__dev_bridge = state

  install_print_hook()
  install_sink()

  local unload = renoise.tool().tool_will_unload_observable
  if not unload:has_notifier(Bridge.stop) then
    unload:add_notifier(Bridge.stop)
  end

  _G.dev = Bridge.helpers
  try_bind()
end

-- Helpers available to `eval` code as the global `dev` ----------------------

Bridge.helpers = {}

---First visible registered dialog, or the one with the given name.
---@param name string?
---@return renoise.Dialog?
function Bridge.helpers.dialog(name)
  if not APP or not APP.dialogs then
    return nil
  end
  if name then
    local entry = APP.dialogs[name]
    return entry and entry.dialog or nil
  end
  for _, entry in pairs(APP.dialogs) do
    if entry.dialog.visible then
      return entry.dialog
    end
  end
  return nil
end

---Find a view by its ViewBuilder id across all registered dialogs.
---@param id string
---@return renoise.Views.View?
function Bridge.helpers.view(id)
  if not APP or not APP.dialogs then
    return nil
  end
  for _, entry in pairs(APP.dialogs) do
    local view = entry.vb.views[id]
    if view then
      return view
    end
  end
  return nil
end

---Set a control's value (or text). Assigning `value` fires its notifier, which
---is the only way to "click" a control programmatically.
---@param id string
---@param value any
---@return renoise.Views.View
function Bridge.helpers.set(id, value)
  local view = Bridge.helpers.view(id)
  if not view then
    error("no view with id " .. tostring(id), 2)
  end
  local control = view --[[@as table]]
  local ok = pcall(function()
    control.value = value
  end)
  if not ok then
    control.text = value
  end
  return view
end

---Append a line to the dev log.
function Bridge.helpers.log(...)
  local parts = {}
  for i = 1, select("#", ...) do
    parts[i] = tostring((select(i, ...)))
  end
  record("app", table.concat(parts, "\t"))
end

return Bridge
