--[[
  Bridge home ports. Run with `just test tests/home_port_test.lua`.
  The expected numbers come from `home_port()` in scripts/renoise.py: both
  sides must agree, or the CLI looks for the bridge on the wrong port.
  (The ids are fixed examples on purpose: `just init` rewrites the template's
  placeholder id in every text file, so it must not appear here.)
]]

local t = require "tests.helper"
local home_port = require "dev.home_port"

t.eq(home_port.for_tool "com.yourname.ToolName", 18898, "example id")
t.eq(home_port.for_tool "com.dac514.MidiDrop", 18867, "MidiDrop")
t.eq(home_port.for_tool "com.dac514.AsciiDancer", 18912, "AsciiDancer")

local p = home_port.for_tool "x"
t.check(p >= home_port.BASE and p < home_port.BASE + home_port.SPAN, "inside the range")

t.eq(
  home_port.tool_id "/home/me/Tools/com.yourname.ToolName.xrnx/",
  "com.yourname.ToolName",
  "posix path"
)
t.eq(
  home_port.tool_id [[C:\Users\me\Tools\com.yourname.ToolName.xrnx\]],
  "com.yourname.ToolName",
  "windows path"
)
t.eq(
  home_port.tool_id "/home/me/Tools/com.yourname.ToolName.xrnx",
  "com.yourname.ToolName",
  "no trailing slash"
)
t.eq(home_port.tool_id "/home/me/elsewhere/", nil, "not a bundle")

t.done()
