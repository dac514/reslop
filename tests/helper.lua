--[[
  Minimal test helper for `just test`. No framework to install: a test file
  requires this, calls `check`/`eq`, and ends with `done()`, which exits
  non-zero when anything failed.

  `just test` runs every `tests/*_test.lua` under plain LuaJIT with the tool
  bundle on `package.path`, so tests `require "src.x"` exactly like the tool
  does. Modules under test must stay pure Lua: no `renoise.*` and no Renoise
  additions to the standard library (`table.find`, `oprint`, ...), because
  those only exist inside Renoise.
]]

local M = {}

local checks, failures = 0, 0

---@param value any
---@return string
local function show(value)
  if type(value) == "string" then
    return ("%q"):format(value)
  end
  return tostring(value)
end

---Record one check. Prints `FAIL: <msg>` when `cond` is false.
---@param cond any
---@param msg string
---@return boolean
function M.check(cond, msg)
  checks = checks + 1
  if not cond then
    failures = failures + 1
    print("FAIL: " .. msg)
    return false
  end
  return true
end

---Check `got == want` and print both values when they differ.
---@param got any
---@param want any
---@param msg string
---@return boolean
function M.eq(got, want, msg)
  return M.check(got == want, ("%s: got %s, want %s"):format(msg, show(got), show(want)))
end

---Check that `fn` raises an error (optionally matching `pattern`).
---@param fn function
---@param pattern string|nil Lua pattern the error message must match.
---@param msg string
---@return boolean
function M.fails(fn, pattern, msg)
  local ok, err = pcall(fn)
  if ok then
    return M.check(false, msg .. ": expected an error, got none")
  end
  if pattern and not tostring(err):find(pattern) then
    return M.check(false, ("%s: error %s does not match %q"):format(msg, show(err), pattern))
  end
  checks = checks + 1
  return true
end

---Print the summary and exit the process: 0 when every check passed, 1 otherwise.
function M.done()
  print(("%d checks, %d failed"):format(checks, failures))
  os.exit(failures == 0 and 0 or 1)
end

return M
