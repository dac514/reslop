--[[
  Each tool's own bridge port, worked out from its tool id, so several tools in
  development can run side by side without fighting over one port. Pure Lua:
  `tests/home_port_test.lua` checks it against `home_port()` in
  scripts/renoise.py, which must compute the same number.

    port = BASE + (hash(id) % SPAN)   hash: h = (h * 31 + byte) % 65521

  The bridge tries its home port first (and retries it, because Renoise frees a
  closed socket a moment late), then the next few ports. `dev/port` still
  overrides it.
]]

local M = {}

M.BASE = 18765
M.SPAN = 200

---The tool id (`com.you.Tool`) from a bundle path like `/x/Tools/com.you.Tool.xrnx/`.
---@param bundle_path string
---@return string|nil
function M.tool_id(bundle_path)
  return bundle_path:match "([^/\\]+)%.xrnx[/\\]*$"
end

---@param tool_id string
---@return integer
function M.for_tool(tool_id)
  local h = 0
  for i = 1, #tool_id do
    h = (h * 31 + tool_id:byte(i)) % 65521
  end
  return M.BASE + h % M.SPAN
end

return M
