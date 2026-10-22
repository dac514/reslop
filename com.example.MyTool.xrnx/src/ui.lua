--[[
  ViewBuilder UI for the main dialog. Pure construction: returns the builder (so
  the dev bridge can map ids to views) and the root view.
]]

local M = {}

---@param app table The application module (`src/app.lua`).
---@return renoise.ViewBuilder vb, renoise.Views.View root
function M.build(app)
  local vb = renoise.ViewBuilder()
  local prefs = app.prefs()
  local song = renoise.song()

  local function song_text()
    if not song then
      return "Song: (none)"
    end
    return "Song: " .. (song.name ~= "" and song.name or "(untitled)")
  end

  local function bpm_text()
    return song and ("BPM: %d"):format(song.transport.bpm) or "BPM: -"
  end

  local root = vb:column {
    id = "root",
    margin = renoise.ViewBuilder.DEFAULT_DIALOG_MARGIN,
    spacing = renoise.ViewBuilder.DEFAULT_CONTROL_SPACING,
    vb:text { id = "song_name", font = "bold", text = song_text() },
    vb:text { id = "bpm", text = bpm_text() },
    vb:row {
      spacing = renoise.ViewBuilder.DEFAULT_CONTROL_SPACING,
      vb:text { text = "Greeting" },
      vb:textfield { id = "greeting", width = 220, bind = prefs.greeting },
    },
    vb:button {
      id = "say_hello",
      text = "Say hello",
      notifier = app.guard(function()
        renoise.app():show_status(prefs.greeting.value)
      end),
    },
  }

  if song then
    local bpm_view = vb.views.bpm --[[@as renoise.Views.Text]]
    app.reg.notifier(song.transport.bpm_observable, function()
      bpm_view.text = bpm_text()
    end)
  end

  return vb, root
end

return M
