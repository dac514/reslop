# Upgrading a project made from ReSlop

ReSlop is a template. When you click *Use this template*, your project gets a
copy of the kit as it was on that day. Later fixes to the kit do not reach your
project by themselves. This page lists those fixes, newest first, and how to
bring each one into a project you already have.

Each entry has a prompt you can paste into Claude Code (or another coding
assistant) inside your project. It reads the new files from ReSlop, keeps any
changes you made to your copies, and checks the result. You can also do it by
hand; the steps are listed too.

In the commands below, `<Id>.xrnx` is your tool's folder, for example
`com.yourname.ToolName.xrnx`.

## 2026-11: several tools in development at once

**The problem.** Every tool made from ReSlop has a dev bridge, and every bridge
wanted the same port, 18765. With two or three tools installed in Renoise, the
bridges took turns on 18765, 18766, 18767, and the order changed with every
reload. `renoise.py` did not check *which* tool answered. So `just eval` could
run your code inside a different tool, and `just reload` could report success
after hearing from the wrong one.

**The fix.**
- Each bridge now listens on its own **home port**, worked out from the tool id
  (somewhere between 18765 and 18964). Nothing to configure.
- `renoise.py` pings the likely ports and only talks to the bridge that reports
  your tool id. If it finds only other tools, it waits a moment, then tells you
  which tools it found.
- A bridge refuses any request that is meant for a different tool.
- `--port N` still reaches any bridge, when you want that on purpose.

Old and new bridges can run side by side, so you can upgrade one project at a
time.

**Needs** `tests/helper.lua` and `just test` from the 2026-10 entry below. Made
your project before 26 October 2026? Do that entry first (the prompt below
checks for you).

**Files:**
- `<Id>.xrnx/dev/home_port.lua` (new)
- `<Id>.xrnx/dev/bridge.lua`
- `<Id>.xrnx/dev/commands.lua`
- `scripts/renoise.py`
- `tests/home_port_test.lua` (new)

**Prompt for your coding assistant:**

```text
Bring the "several tools in development at once" fix from ReSlop into this project,
following the 2026-11 entry of https://github.com/dac514/reslop/blob/main/UPGRADING.md.
If tests/helper.lua does not exist here yet, apply the 2026-10 entry first.
Clone https://github.com/dac514/reslop (main) into a temporary folder. From it, take
*.xrnx/dev/home_port.lua, *.xrnx/dev/bridge.lua, *.xrnx/dev/commands.lua,
scripts/renoise.py and tests/home_port_test.lua. Before replacing a file, diff it with
this project's copy; if this project changed it, merge instead of overwriting. The tool
folder here has a different name than ReSlop's; keep ours. Remove any dev/port file or
RENOISE_DEV_PORT setting that pins the old port 18765, unless it was set on purpose.
Then run just check, just test, just reload and just ping. ping must show tool_id with
this tool's id and a port other than 18765. Show me the diff before committing.
```

**By hand** (macOS, Linux, WSL; on Windows use the same steps in Git Bash):

```sh
git clone --depth 1 https://github.com/dac514/reslop.git /tmp/reslop
diff -r /tmp/reslop/*.xrnx/dev <Id>.xrnx/dev          # see what changed
cp /tmp/reslop/*.xrnx/dev/home_port.lua /tmp/reslop/*.xrnx/dev/bridge.lua \
   /tmp/reslop/*.xrnx/dev/commands.lua <Id>.xrnx/dev/
cp /tmp/reslop/scripts/renoise.py scripts/
cp /tmp/reslop/tests/home_port_test.lua tests/
just check && just test && just reload && just ping
```

`just ping` should now print `tool_id=<your tool id>` and a port other than
18765. If you changed `bridge.lua`, `commands.lua` or `renoise.py` in your
project, merge those changes back in instead of copying over them.

## 2026-10: unit tests that run without Renoise

**The problem.** The first ReSlop (22 October 2026) had no way to test logic
outside Renoise. Every check needed a running Renoise and a reload.

**The fix.** `just test` runs every `tests/*_test.lua` file under plain LuaJIT,
with your tool folder on `package.path`, so a test can `require "src.x"` the
same way the tool does. No Renoise needed. A tiny `tests/helper.lua` gives you
`check`, `eq`, `fails` and `done`. CI runs the tests on every push.
`just test tests/x_test.lua` runs one file, and anything after `--` goes to the
test (`just test tests/x_test.lua -- --verbose`).

The rule that comes with it: logic worth testing lives in a **pure module**, a
file under `src/` that uses no `renoise.*` and none of Renoise's additions to
the Lua standard library (`table.find`, `oprint`, ...). `just test` runs
outside Renoise, where those do not exist.

**Files:**
- `tests/helper.lua` (new)
- `scripts/renoise.py` (adds the `test` command, and `doctor` checks for LuaJIT)
- `justfile`: a `test` recipe
- `.github/workflows/ci.yml`: install LuaJIT, then run the tests
- optional, as a worked example: ReSlop's `tests/labels_test.lua` and
  `*.xrnx/src/labels.lua`. They test the template's own dialog, so only copy
  them if your tool still has that dialog.

Already have tests of your own, run some other way? Keep them. The runner
accepts any `tests/*_test.lua` file that exits non-zero on failure. If a test
sets its own `package.path`, that still works.

**Prompt for your coding assistant:**

```text
Bring the "unit tests that run without Renoise" setup from ReSlop into this project,
following the 2026-10 entry of https://github.com/dac514/reslop/blob/main/UPGRADING.md.
Clone https://github.com/dac514/reslop (main) into a temporary folder. Copy
tests/helper.lua. Take scripts/renoise.py from it; diff it with this project's copy first,
and if this project changed it, merge instead of overwriting. Add the `test *ARGS` recipe
from ReSlop's justfile, and the "Install LuaJIT" and "Unit tests" steps from ReSlop's
.github/workflows/ci.yml. If this project already has a test recipe or test step, replace
it with ReSlop's runner, and check that this project's existing tests still pass under
`just test`. Keep the old way to run them in the docs if it still works. Update CLAUDE.md's
command table and directory map to match. Then run just check and just test, and show me
the diff before committing.
```

**By hand:**

```sh
git clone --depth 1 https://github.com/dac514/reslop.git /tmp/reslop
cp /tmp/reslop/tests/helper.lua tests/
diff /tmp/reslop/scripts/renoise.py scripts/renoise.py   # changed it? merge by hand
cp /tmp/reslop/scripts/renoise.py scripts/
```

Then add these to your `justfile`:

```just
# Unit tests: tests/*_test.lua under LuaJIT, no Renoise needed. just test [FILE ...] [-- ARGS]
test *ARGS:
    {{rn}} test {{ARGS}}
```

and these steps to `.github/workflows/ci.yml`, after the type check:

```yaml
      - name: Install LuaJIT
        run: sudo apt-get update -qq && sudo apt-get install -y -qq luajit

      - name: Unit tests
        run: python3 scripts/renoise.py test
```

Run `just doctor` to see whether LuaJIT is installed (it gives install hints
for your system), then `just test`.
