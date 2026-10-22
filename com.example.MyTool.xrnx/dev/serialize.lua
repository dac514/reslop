--[[
  Serializers used by the dev bridge: Lua values (rprint-like, returned as a
  string instead of printed) and ViewBuilder view trees.
]]

local M = {}

---@param s string
---@return string
local function quote(s)
  local escaped = s:gsub('[%c"\\]', function(c)
    if c == "\n" then
      return "\\n"
    elseif c == "\r" then
      return "\\r"
    elseif c == "\t" then
      return "\\t"
    elseif c == '"' then
      return '\\"'
    elseif c == "\\" then
      return "\\\\"
    end
    return ("\\%03d"):format(c:byte())
  end)
  return '"' .. escaped .. '"'
end
M.quote = quote

local function sorted_keys(t)
  local keys = {}
  for k in pairs(t) do
    keys[#keys + 1] = k
  end
  table.sort(keys, function(a, b)
    local ta, tb = type(a), type(b)
    if ta == tb and (ta == "number" or ta == "string") then
      return a < b
    end
    if ta == "number" then
      return true
    end
    if tb == "number" then
      return false
    end
    return tostring(a) < tostring(b)
  end)
  return keys
end

local function is_array(t)
  local n = #t
  if n == 0 then
    return next(t) == nil
  end
  local count = 0
  for _ in pairs(t) do
    count = count + 1
  end
  return count == n
end

---@class SerializeOptions
---@field depth integer? Maximum nesting depth (default 4)
---@field max_items integer? Maximum entries rendered per table (default 100)

---Render any Lua value (including Renoise API objects) as readable text.
---@param v any
---@param opts SerializeOptions?
---@return string
function M.value(v, opts)
  opts = opts or {}
  local max_depth = opts.depth or 4
  local max_items = opts.max_items or 100
  local seen = {}

  ---@param x any
  ---@param depth integer
  ---@param indent string
  ---@return string
  local function render(x, depth, indent)
    local t = type(x)
    if t == "string" then
      return quote(x)
    elseif t == "number" or t == "boolean" or t == "nil" then
      return tostring(x)
    elseif t == "function" or t == "thread" or t == "userdata" then
      return "<" .. tostring(x) .. ">"
    elseif t == "table" then
      if seen[x] then
        return "<cycle>"
      end
      if depth >= max_depth then
        return "{...}"
      end
      seen[x] = true
      local keys = sorted_keys(x)
      if #keys == 0 then
        seen[x] = nil
        return "{}"
      end
      local pad = indent .. "  "
      local parts = {}
      local array = is_array(x)
      for i, k in ipairs(keys) do
        if i > max_items then
          parts[#parts + 1] = pad .. ("...(+%d)"):format(#keys - max_items)
          break
        end
        local val = render(x[k], depth + 1, pad)
        if array then
          parts[#parts + 1] = pad .. val
        else
          local key
          if type(k) == "string" and k:match "^[%a_][%w_]*$" then
            key = k
          else
            key = "[" .. render(k, max_depth, "") .. "]"
          end
          parts[#parts + 1] = pad .. key .. " = " .. val
        end
      end
      seen[x] = nil
      return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
    end
    -- Renoise API object: type() returns its class name.
    return "<" .. t .. ">"
  end

  return render(v, 0, "")
end

-- View trees -----------------------------------------------------------------

local PROBE = { "text", "value", "items", "min", "max", "active", "edit_mode", "tooltip" }

---Read a property that may not exist on this view class.
---@param view renoise.Views.View
---@param key string
---@return any value, boolean ok
local function probe(view, key)
  local ok, val = pcall(function()
    return view[key]
  end)
  if ok then
    return val, true
  end
  return nil, false
end

---Find the ViewBuilder id of a view. Views do not implement `==`, but
---Renoise's `rawequal` understands API objects, so search the builder's id map.
---@param view renoise.Views.View
---@param views_by_id table<string, renoise.Views.View>
---@return string?
local function id_of(view, views_by_id)
  for id, candidate in pairs(views_by_id) do
    if rawequal(candidate, view) then
      return id
    end
  end
  return nil
end

---Render a view hierarchy, one node per line.
---@param root renoise.Views.View
---@param views_by_id table<string, renoise.Views.View> Usually `vb.views`.
---@return string
function M.view_tree(root, views_by_id)
  local lines = {}

  local function walk(view, indent)
    local parts = { type(view) }
    local id = id_of(view, views_by_id)
    if id then
      parts[#parts + 1] = "#" .. id
    end
    local w, okw = probe(view, "width")
    local h, okh = probe(view, "height")
    if okw and okh then
      parts[#parts + 1] = ("%sx%s"):format(tostring(w), tostring(h))
    end
    local visible, okv = probe(view, "visible")
    if okv then
      parts[#parts + 1] = visible and "visible" or "HIDDEN"
    end
    for _, key in ipairs(PROBE) do
      local val, ok = probe(view, key)
      if ok and val ~= nil and not (key == "tooltip" and val == "") then
        local rendered
        if type(val) == "string" then
          rendered = quote(val)
        else
          rendered = M.value(val, { depth = 1, max_items = 20 })
          rendered = (rendered:gsub("\n%s*", " "))
        end
        parts[#parts + 1] = key .. "=" .. rendered
      end
    end
    lines[#lines + 1] = indent .. table.concat(parts, " ")
    local children = probe(view, "views")
    if type(children) == "table" then
      for _, child in ipairs(children) do
        walk(child, indent .. "  ")
      end
    end
  end

  walk(root, "")
  return table.concat(lines, "\n")
end

return M
