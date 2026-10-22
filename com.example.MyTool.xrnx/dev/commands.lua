--[[
  Request handlers for the dev bridge. Each handler receives the request records
  (string -> string) and the bridge state, and returns a table of reply records.
  `status` defaults to "ok" unless the handler sets it.
]]

local serialize = require "dev.serialize"

local M = {}

---@param _ table
---@param ctx BridgeState
function M.ping(_, ctx)
  local visible = 0
  if APP and APP.dialogs then
    for _, entry in pairs(APP.dialogs) do
      if entry.dialog.visible then
        visible = visible + 1
      end
    end
  end
  return {
    boot_id = ctx.boot_id,
    reload_count = tostring(ctx.reload_count),
    port = tostring(ctx.port),
    bind = ctx.bind,
    bundle_path = ctx.bundle_path,
    renoise_version = renoise.RENOISE_VERSION,
    api_version = tostring(renoise.API_VERSION),
    platform = os.platform(),
    song_loaded = tostring(renoise.song() ~= nil),
    dialogs_visible = tostring(visible),
  }
end

---@param req table
---@param ctx BridgeState
function M.eval(req, ctx)
  local code = req.code
  if not code then
    return { status = "error", error = "missing 'code' record" }
  end
  local fn, err = loadstring("return " .. code, "=eval")
  if not fn then
    fn, err = loadstring(code, "=eval")
  end
  if not fn then
    return { status = "error", error = "syntax: " .. tostring(err) }
  end
  local t0 = os.clock()
  local output, results = ctx.capture(fn)
  local ms = ("%d"):format((os.clock() - t0) * 1000)
  if not results[1] then
    local message = results[2] and tostring(results[2]) or "unknown error"
    ctx.ring:push("error", message)
    return { status = "error", error = message, output = output, ms = ms }
  end
  local rendered = {}
  for i = 2, results.n do
    rendered[#rendered + 1] = serialize.value(results[i])
  end
  return { output = output, result = table.concat(rendered, "\n"), ms = ms }
end

---Soft reload: stop the running APP, drop `src.*` from package.loaded, require
---and start it again. main.lua, manifest.xml and dev/ are NOT reloaded.
---@param _ table
---@param ctx BridgeState
function M.reload(_, ctx)
  local output, results = ctx.capture(function()
    if APP and APP.stop then
      local ok, err = pcall(APP.stop)
      if not ok then
        ctx.ring:push("error", "APP.stop failed: " .. tostring(err))
      end
    end
    for name in pairs(package.loaded) do
      if type(name) == "string" and name:match "^src[%./]" then
        package.loaded[name] = nil
      end
    end
    APP = require "src.app"
    ctx.install_sink()
    APP.start()
  end)
  if not results[1] then
    local message = results[2] and tostring(results[2]) or "unknown error"
    ctx.ring:push("error", message)
    return { status = "error", error = message, output = output }
  end
  ctx.reload_count = ctx.reload_count + 1
  return { output = output, reload_count = tostring(ctx.reload_count) }
end

---@param req table
function M.views(req)
  if not APP or not APP.dialogs then
    return { status = "error", error = "APP.dialogs is not available" }
  end
  local want = req.dialog
  local all = req.all == "1"
  local names = {}
  for name in pairs(APP.dialogs) do
    names[#names + 1] = name
  end
  table.sort(names)
  local chunks, count = {}, 0
  for _, name in ipairs(names) do
    local entry = APP.dialogs[name]
    if (not want or want == name) and (all or entry.dialog.visible) then
      count = count + 1
      chunks[#chunks + 1] = ("== dialog %q (%s)"):format(
        name,
        entry.dialog.visible and "visible" or "closed"
      )
      chunks[#chunks + 1] = serialize.view_tree(entry.root, entry.vb.views)
    end
  end
  if count == 0 then
    if want then
      chunks[#chunks + 1] = ("no visible dialog named %q"):format(want)
    else
      chunks[#chunks + 1] = "no visible registered dialogs (open one first, or pass all=1)"
    end
  end
  return { tree = table.concat(chunks, "\n"), count = tostring(count) }
end

---@param req table
---@param ctx BridgeState
function M.log(req, ctx)
  local n = tonumber(req.n) or 50
  local entries = ctx.ring:tail(n)
  local lines = {}
  for _, e in ipairs(entries) do
    lines[#lines + 1] = ("%s %-6s %s"):format(os.date("%H:%M:%S", e.t), e.kind, e.text)
  end
  if req.clear == "1" then
    ctx.ring:clear()
  end
  return { entries = table.concat(lines, "\n"), count = tostring(#entries) }
end

function M.song()
  local song = renoise.song()
  if not song then
    return { summary = "no song loaded" }
  end
  local t = song.transport
  local lines = {
    ("name: %s"):format(song.name ~= "" and song.name or "(untitled)"),
    ("bpm: %g  lpb: %d  playing: %s  edit_mode: %s"):format(
      t.bpm,
      t.lpb,
      tostring(t.playing),
      tostring(t.edit_mode)
    ),
    ("tracks: %d  instruments: %d  patterns: %d  sequence length: %d"):format(
      #song.tracks,
      #song.instruments,
      #song.patterns,
      #song.sequencer.pattern_sequence
    ),
    ("selected: track %d  instrument %d  pattern %d  line %d"):format(
      song.selected_track_index,
      song.selected_instrument_index,
      song.selected_pattern_index,
      song.selected_line_index
    ),
  }
  return { summary = table.concat(lines, "\n") }
end

---@param dir string Absolute directory with trailing slash.
---@param rel string Relative prefix for display.
---@param out { path: string, rel: string }[]
local function lua_files(dir, rel, out)
  for _, f in ipairs(os.filenames(dir, { "*.lua" })) do
    out[#out + 1] = { path = dir .. f, rel = rel .. f }
  end
  for _, d in ipairs(os.dirnames(dir)) do
    lua_files(dir .. d .. "/", rel .. d .. "/", out)
  end
end

---Syntax-check main.lua and src/**/*.lua with the real LuaJIT parser (no execution).
---@param req table
---@param ctx BridgeState
function M.check(req, ctx)
  local files = { { path = ctx.bundle_path .. "main.lua", rel = "main.lua" } }
  if io.exists(ctx.bundle_path .. "src") then
    lua_files(ctx.bundle_path .. "src/", "src/", files)
  end
  local errors, checked = {}, 0
  for _, f in ipairs(files) do
    if not req.file or f.rel == req.file then
      local fh = io.open(f.path, "rb")
      if fh then
        local src = fh:read "*a"
        fh:close()
        checked = checked + 1
        local ok, err = loadstring(src, "@" .. f.rel)
        if not ok then
          errors[#errors + 1] = tostring(err)
        end
      end
    end
  end
  local reply = { errors = table.concat(errors, "\n"), files = tostring(checked) }
  if #errors > 0 then
    reply.status = "error"
    reply.error = ("%d syntax error(s)"):format(#errors)
  end
  return reply
end

return M
