# Upgrading a project made from ReSlop

ReSlop is a template. *Use this template* gives your project a copy of the kit as it was
on that day, and later fixes do not reach your project by themselves. This page lists
those fixes, newest first.

## How to apply an entry

Paste the entry's prompt into Claude Code (or another coding assistant) inside your
project, or follow its steps by hand. These rules apply to every entry:

- `<Id>.xrnx` is your tool's folder, for example `com.yourname.ToolName.xrnx`. ReSlop's
  folder has a different name. Keep yours, and keep your ids.
- The steps take kit files from a copy of ReSlop's main branch. On Windows, use Git Bash.
  `git clone --depth 1 https://github.com/dac514/reslop.git /tmp/reslop`
- Diff each kit file with your copy before replacing it. If your project changed it,
  merge instead of overwriting it.
- Skip an entry whose changes your project already has.
- Run the checks the entry names. An assistant shows you the diff before committing.

## 2026-11: shorter CLAUDE.md

**The problem.** Claude Code loads `CLAUDE.md` in every session. The kit's copy had grown
to 18.8 KB, and several facts in it were stated two or three times. That cost about 1,000
tokens in every session, for no gain.

**The fix.** ReSlop's `CLAUDE.md` now states each fact once. The setup steps moved to
`docs/setup.md` and the renoise.com rules to `docs/publishing.md`, which Claude reads only
when needed. Their headings stay in `CLAUDE.md`, each with a one-line pointer. No rule was
dropped and no code changed, so this entry is optional.

**Steps:**

1. Apply the older entries first. ReSlop's `CLAUDE.md` describes their files, such as
   `dev/home_port.lua` and `tests/helper.lua`.
2. Copy `docs/setup.md` and `docs/publishing.md` from ReSlop.
   ```sh
   mkdir -p docs && cp /tmp/reslop/docs/setup.md /tmp/reslop/docs/publishing.md docs/
   ```
3. Find what your project added to `CLAUDE.md`. Your first commit has the kit's copy, so
   this diff shows your own notes. It also shows kit fixes from earlier entries.
   ```sh
   git diff $(git rev-list --max-parents=0 HEAD) -- CLAUDE.md
   ```
4. Replace the kit text in your `CLAUDE.md` with ReSlop's, and keep your own notes. The
   first section of ReSlop's copy names the template's placeholder folder. Put your own
   folder name there.
5. Read `git diff CLAUDE.md`. Every heading of your old file must still be there, and
   every removed line must be kit text that ReSlop removed or moved to `docs/`.
6. If your `README.md` says that `CLAUDE.md` lists the renoise.com rules, point it at
   `docs/publishing.md` instead.

**Prompt:** `Apply the "2026-11: shorter CLAUDE.md" entry of https://github.com/dac514/reslop/blob/main/UPGRADING.md, following the rules at the top of that page.`

## 2026-11: publishing on renoise.com

**The problem.** The renoise.com tool page is built from the uploaded `.xrnx`, not from
the fields you can edit on the site. It shows the tool's `README.md` and takes its images
from `cover.png` and `thumbnail.png` in the archive. The site stretches images of other
sizes, so a tall dialog screenshot comes out squashed. The tools list cuts the manifest
`<Description>` at 120 characters. The template ships no images on purpose.

**The fix.** `docs/publishing.md` lists the site's rules and a check before uploading.

**Steps:**

1. Copy `docs/publishing.md` from ReSlop. Add the *Publishing on renoise.com* section and
   the `docs/publishing.md` and `cover.png` lines of the directory map from ReSlop's
   `CLAUDE.md` to yours. If yours already has the longer section from an earlier version
   of this entry, you can replace it with the short one. The paragraph about renoise.com in
   *Day to day* in ReSlop's `README.md` is optional.
2. Check your tool against `docs/publishing.md`. Count the characters of `<Description>`
   in `manifest.xml`. Report whether `cover.png` and `thumbnail.png` exist in the tool
   folder, and their size. An assistant does not draw images unless you ask.
   ```sh
   file <Id>.xrnx/cover.png <Id>.xrnx/thumbnail.png
   ```
3. Before you upload, check that `cover.png`, `thumbnail.png` and `README.md` are at the
   root of the package.
   ```sh
   just package && unzip -l dist/<Id>.xrnx
   ```

**Prompt:** `Apply the "2026-11: publishing on renoise.com" entry of https://github.com/dac514/reslop/blob/main/UPGRADING.md, following the rules at the top of that page.`

## 2026-11: tools that fail to load when Renoise starts

**The problem.** Renoise loads tools before it has finished starting. In that phase, any
use of `renoise.app().theme` or `renoise.app().theme_observable` raises "can not access
the application theme while the application initializes", and the tool fails to load.
`just install` and `just reload` run on a Renoise that is already up, so only a fresh
start of Renoise shows the error. A tool can pass every check and still fail for everyone
who installs it.

Your tool is affected when `App.start()`, or code at module level, reads the theme. One
example is a notifier on `theme_observable` that lets a dialog follow theme changes. The
template itself is not affected.

**The fix.** Only the theme is known to fail, but registering all `renoise.app()`
observables when a dialog first opens avoids the whole problem. Before you tag a release,
quit Renoise and start it again once.

**Steps:**

1. From ReSlop, copy the startup bullet of *Renoise facts learned while building this kit*
   and the restart line of the *Git* section into your `CLAUDE.md`. Copy the startup rule
   at the top of `src/app.lua` into yours (a comment only).
2. Search `App.start()`, everything it calls, and module-level code in `src/` for
   `renoise.app().theme` and `theme_observable`. Move each use into the code that opens
   your dialog.
   ```sh
   grep -rn "theme" <Id>.xrnx/src
   ```
3. Run `just check` and `just reload`.
4. Quit Renoise, start it again, and check that no "Scripting Tool Error" appears. An
   assistant asks you to do this step.

**Prompt:** `Apply the "2026-11: tools that fail to load when Renoise starts" entry of https://github.com/dac514/reslop/blob/main/UPGRADING.md, following the rules at the top of that page.`

## 2026-11: several tools in development at once

**The problem.** Every tool made from ReSlop has a dev bridge, and every bridge wanted
port 18765. With two or three tools installed, the bridges took turns on 18765, 18766 and
18767, and the order changed with every reload. `renoise.py` did not check *which* tool
answered. So `just eval` could run your code inside a different tool, and `just reload`
could report success after hearing from the wrong one.

**The fix.** Each bridge now listens on its own **home port**, worked out from the tool
id (somewhere between 18765 and 18964). You do not configure anything. `renoise.py` pings the
likely ports and only talks to the bridge that reports your tool id. If it finds only
other tools, it waits a moment, then tells you which tools it found. A bridge refuses any
request meant for a different tool. `--port N` still reaches any bridge, when you want
that on purpose. Old and new bridges can run side by side, so you can upgrade one project
at a time.

**Steps:**

1. If `tests/helper.lua` does not exist yet, apply the 2026-10 entry first.
2. Take these files from ReSlop: `*.xrnx/dev/home_port.lua` (new),
   `*.xrnx/dev/bridge.lua`, `*.xrnx/dev/commands.lua`, `scripts/renoise.py` and
   `tests/home_port_test.lua` (new). The `cp` lines overwrite your files, so merge by hand
   any file your project changed.
   ```sh
   diff -r /tmp/reslop/*.xrnx/dev <Id>.xrnx/dev
   cp /tmp/reslop/*.xrnx/dev/home_port.lua /tmp/reslop/*.xrnx/dev/bridge.lua \
      /tmp/reslop/*.xrnx/dev/commands.lua <Id>.xrnx/dev/
   cp /tmp/reslop/scripts/renoise.py scripts/
   cp /tmp/reslop/tests/home_port_test.lua tests/
   ```
3. Remove any `dev/port` file or `RENOISE_DEV_PORT` setting that pins the old port 18765,
   unless it was set on purpose.
4. Run `just check && just test && just reload && just ping`. `just ping` must print
   `tool_id=<your tool id>` and a port other than 18765.

**Prompt:** `Apply the "2026-11: several tools in development at once" entry of https://github.com/dac514/reslop/blob/main/UPGRADING.md, following the rules at the top of that page.`

## 2026-10: unit tests that run without Renoise

**The problem.** The first ReSlop (22 October 2026) had no way to test logic outside
Renoise. Every check needed a running Renoise and a reload.

**The fix.** `just test` runs every `tests/*_test.lua` file under plain LuaJIT, with your
tool folder on `package.path`, so a test can `require "src.x"` the same way the tool
does. A tiny `tests/helper.lua` gives you `check`, `eq`, `fails` and `done`. CI runs the
tests on every push, and `just doctor` checks for LuaJIT. `just test tests/x_test.lua`
runs one file, and anything after `--` goes to the test
(`just test tests/x_test.lua -- --verbose`).

The rule that comes with it: logic worth testing lives in a **pure module**, a file under
`src/` that uses no `renoise.*` and none of Renoise's additions to the Lua standard
library (`table.find`, `oprint`, ...). `just test` runs outside Renoise, where those do
not exist.

**Steps:**

1. Copy `tests/helper.lua` and `scripts/renoise.py` from ReSlop. Diff `renoise.py` first;
   if you changed it, merge by hand.
   ```sh
   cp /tmp/reslop/tests/helper.lua tests/
   diff /tmp/reslop/scripts/renoise.py scripts/renoise.py
   cp /tmp/reslop/scripts/renoise.py scripts/
   ```
2. Add this recipe to your `justfile`, in place of any test recipe it already has:
   ```just
   # Unit tests: tests/*_test.lua under LuaJIT, no Renoise needed. just test [FILE ...] [-- ARGS]
   test *ARGS:
       {{rn}} test {{ARGS}}
   ```
3. Add these steps to `.github/workflows/ci.yml` after the type check, in place of any
   test step it already has:
   ```yaml
         - name: Install LuaJIT
           run: sudo apt-get update -qq && sudo apt-get install -y -qq luajit

         - name: Unit tests
           run: python3 scripts/renoise.py test
   ```
4. Already have tests of your own, run some other way? Keep them, and check that they
   pass under `just test`. The runner accepts any `tests/*_test.lua` file that exits
   non-zero on failure, and a test that sets its own `package.path` still works. If the
   old way to run them still works, keep it in the docs.
5. Update the command table, the directory map and the pure-module rule under *Hard
   constraints* in your `CLAUDE.md` to match ReSlop's.
6. Run `just doctor`, which says whether LuaJIT is installed and how to get it. Then run
   `just check` and `just test`.

Optional worked example: ReSlop's `tests/labels_test.lua` and `*.xrnx/src/labels.lua`.
They test the template's own dialog, so only copy them if your tool still has that dialog.

**Prompt:** `Apply the "2026-10: unit tests that run without Renoise" entry of https://github.com/dac514/reslop/blob/main/UPGRADING.md, following the rules at the top of that page.`
