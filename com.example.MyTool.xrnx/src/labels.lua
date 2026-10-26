--[[
  Label text for the main dialog. Pure Lua on purpose: no `renoise.*`, no
  Renoise additions to the standard library, so `just test` can run it under
  plain LuaJIT without Renoise. `src/ui.lua` reads the song and hands the plain
  values in here.
]]

local M = {}

---@param name string|nil The song name, or nil when no song is loaded.
---@return string
function M.song(name)
  if name == nil then
    return "Song: (none)"
  end
  return "Song: " .. (name ~= "" and name or "(untitled)")
end

---@param bpm number|nil
---@return string
function M.bpm(bpm)
  if bpm == nil then
    return "BPM: -"
  end
  return ("BPM: %d"):format(bpm)
end

---@class TrackSummary
---@field sequencer integer Number of sequencer tracks.
---@field sends integer Number of send tracks.
---@field last_name string Name of the last track.
---@field last_empty boolean Whether the last track of pattern 1 is empty.

---@param summary TrackSummary|nil
---@return string
function M.tracks(summary)
  if summary == nil then
    return "Tracks: -"
  end
  return ("Tracks: %d · Sends: %d · %s in pattern 1: %s"):format(
    summary.sequencer,
    summary.sends,
    summary.last_name,
    summary.last_empty and "empty" or "in use"
  )
end

return M
