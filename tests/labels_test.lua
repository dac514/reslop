--[[
  Example unit test. Run with `just test` (all files) or
  `just test tests/labels_test.lua` (this one). No Renoise needed.
]]

local t = require "tests.helper"
local labels = require "src.labels"

t.eq(labels.song(nil), "Song: (none)", "song: no song loaded")
t.eq(labels.song "", "Song: (untitled)", "song: unnamed song")
t.eq(labels.song "Demo", "Song: Demo", "song: named song")

t.eq(labels.bpm(nil), "BPM: -", "bpm: no song loaded")
t.eq(labels.bpm(128), "BPM: 128", "bpm: integer")
t.eq(labels.bpm(132.9), "BPM: 132", "bpm: fractional values are truncated")

t.eq(labels.tracks(nil), "Tracks: -", "tracks: no song loaded")
t.eq(
  labels.tracks { sequencer = 8, sends = 1, last_name = "Master", last_empty = true },
  "Tracks: 8 · Sends: 1 · Master in pattern 1: empty",
  "tracks: empty last track"
)
t.eq(
  labels.tracks { sequencer = 2, sends = 0, last_name = "Lead", last_empty = false },
  "Tracks: 2 · Sends: 0 · Lead in pattern 1: in use",
  "tracks: last track in use"
)

t.done()
