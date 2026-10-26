--[[
  ViewBuilder UI for the main dialog. Pure construction: returns the builder (so
  the dev bridge can map ids to views) and the root view.
]]

local labels = require "src.labels"

local M = {}

---@param app table The application module (`src/app.lua`).
---@return renoise.ViewBuilder vb, renoise.Views.View root
function M.build(app)
  local vb = renoise.ViewBuilder()
  local prefs = app.prefs()
  local song = renoise.song()

  local function song_text()
    return labels.song(song and song.name)
  end

  local function bpm_text()
    return labels.bpm(song and song.transport.bpm)
  end

  local function tracks_text()
    if not song then
      return labels.tracks(nil)
    end
    local n = #song.tracks
    local last = song:pattern(1):track(n) -- errors inside tracks_observable without App.defer
    return labels.tracks {
      sequencer = song.sequencer_track_count,
      sends = song.send_track_count,
      last_name = song.tracks[n].name,
      last_empty = last.is_empty,
    }
  end

  local root = vb:column {
    id = "root",
    margin = renoise.ViewBuilder.DEFAULT_DIALOG_MARGIN,
    spacing = renoise.ViewBuilder.DEFAULT_CONTROL_SPACING,
    vb:text { id = "song_name", font = "bold", text = song_text() },
    vb:text { id = "bpm", text = bpm_text() },
    vb:text { id = "tracks", text = tracks_text() },
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
    local tracks_view = vb.views.tracks --[[@as renoise.Views.Text]]
    ---@type fun()
    local on_change
    local function refresh_tracks()
      tracks_view.text = tracks_text()
      -- The last pattern track may be new: watch its emptiness so edits show live.
      app.reg.notifier(song:pattern(1):track(#song.tracks).is_empty_observable, on_change)
    end
    -- Fires mid-insert, before patterns have the new track: run after the edit.
    function on_change()
      app.defer(refresh_tracks)
    end
    app.reg.notifier(song.tracks_observable, on_change)
    refresh_tracks()
  end

  return vb, root
end

return M
