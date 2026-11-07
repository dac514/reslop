# CLAUDE.md

This repository is a [Renoise](https://www.renoise.com) tool written in Lua, plus the
command-line tooling to format, type-check, install, reload and inspect it while Renoise runs.

## What you are working on

- The tool is the single `*.xrnx/` folder in the repo root
  (`com.example.MyTool.xrnx/` until `just init` renames it). Everything else is tooling.
- Lua dialect: **LuaJIT** = Lua 5.1 syntax (`unpack`, `loadstring`, `setfenv`;
  `bit` is built in; no `goto`, no `//`, no integer subtype).
- Renoise API version **6.2** (Renoise 3.5). The API reference is vendored in
  `definitions/library/` and the guides in `docs/renoise/`. Prefer those over memory.
- Renoise must be running, with the tool installed, for every command that talks
  to the dev bridge (`ping`, `eval`, `reload`, `views`, `log`, `song`, `check`).

## Commands

All recipes wrap `python3 scripts/renoise.py <cmd>` (stdlib only), so the same
things work without `just`. `renoise.py` prints `ok ...` or `error ...` on the
first line; exit codes: 0 ok, 1 remote/Lua error, 2 usage, 3 cannot connect,
4 timeout, 5 unsupported on this platform. `--json` gives one JSON object.

| command | what it does |
|---|---|
| `just doctor` | check stylua, lua-language-server, just, luajit, Renoise folders, the bridge |
| `just check` | `stylua --check .` + `lua-language-server --check .` (+ Renoise's own parser via the bridge when reachable) |
| `just test` | run `tests/*_test.lua` under plain LuaJIT with the bundle on `package.path`; no Renoise needed. `just test tests/x_test.lua` runs one file, `-- ARGS` go to the test |
| `just fmt` | format all Lua in place |
| `just install` | install into Renoise through OSC `install_tool` (Renoise copies and loads the bundle); falls back to a symlink/copy that needs *Tools > Reload All Tools* once |
| `just reload` | **full reload** (default): zip the bundle (with `dev/`) and `install_tool` it through OSC; fresh Lua state, new `boot_id`, about a second |
| `just reload-soft` | quick reload of `src/` only: sync into the installed copy, `APP.stop()`, drop `src.*` from `package.loaded`, `APP.start()`. It keeps the Lua state, so closures registered outside `App.reg` stay. It does not touch `main.lua`, `manifest.xml` or `dev/`. After a Lua error the old module stays stopped (menus gone) until a reload succeeds |
| `just ping` | bridge alive? prints boot_id, bundle path, Renoise/API version |
| `just eval 'CODE'` | run Lua (an expression or statements) inside the tool's Lua state; prints captured `print` output and `=> value` per return value |
| `just views` | view tree of every open registered dialog: `Type #id WxH visible text=... value=...` |
| `just log` | last prints, errors, bridge messages from inside the tool (`-n 100`, `--clear`) |
| `just song` | one-screen summary of the current song |
| `just screenshot` | PNGs into `dist/`: on X11/XWayland one per Renoise window (dialogs are `-2`, `-3`...), whole screen elsewhere; then Read them |
| `just package` | distributable `dist/<Id>.xrnx` without `dev/` and `preferences.xml` |
| `just init com.you.Name "Name" ["You [you@x.com]"]` | rename the template placeholder once |
| `just update-defs` | refresh `definitions/` and `docs/renoise/` from GitHub |

### The development loop

1. Edit `src/*.lua` (behaviour and UI), `main.lua` (entry), `manifest.xml`, or `dev/*` (bridge).
2. `just check`, and `just test` when a pure module or a test changed. Fix everything they report before reloading.
3. `just reload`. `just reload-soft` is faster for `src/`-only edits, within the limits in the table.
4. Verify inside the running Renoise: `just eval 'APP.show_dialog()'`, `just views`,
   `just eval 'dev.set("greeting", "x")'`, `just log`, `just screenshot`. Do not report a GUI
   change as working until `views` (and, for layout, a screenshot) shows it.
5. `just check` again, then commit.

Eval helpers available as the global `dev`: `dev.dialog([name])`, `dev.view(id)`,
`dev.set(id, value)` (assigning `.value` fires the control's notifier, the only way to
"click" programmatically), `dev.log(...)`. `APP` is the application module.

If `renoise.py` exits 3, Renoise is not running or the tool is not installed/loaded
(`just install`). If its message says it "found other tools instead", this tool's bridge is
still starting (retry in a moment) or not loaded. If it exits 4, Renoise is probably stuck on
a dialog: take a screenshot and tell the user instead of retrying blindly.

## Setting up a fresh machine

When asked to set the project up, read `docs/setup.md` and follow it in order.

## Updating a project made from an older ReSlop

When asked to bring in kit fixes, read `UPGRADING.md` in https://github.com/dac514/reslop (main)
and apply the entries newer than this project, following the rules at the top of that page.
Never rename this project's own `<Id>.xrnx` folder or ids.

## Directory map

```
CLAUDE.md, README.md          this file; human quick start
docs/setup.md                 setting up a fresh machine
docs/publishing.md            the renoise.com rules
UPGRADING.md                  later kit fixes for projects made from an older ReSlop
justfile                      task runner (python3 on POSIX/WSL, python on Windows)
scripts/renoise.py            the CLI behind every recipe, plus paths, uninstall and sync
.luarc.json                   LuaLS: LuaJIT runtime, definitions as library, class plugin
stylua.toml                   2-space, 100 cols, double quotes, call_parentheses = None
definitions/                  vendored renoise/definitions (LuaCATS); UPSTREAM.md records the commit
docs/renoise/                 vendored xrnx guide pages (start/, guide/)
.github/workflows/ci.yml      stylua --check, lua-language-server --check, unit tests, package
.github/workflows/release.yml tag v* -> GitHub release with the .xrnx attached
<Id>.xrnx/manifest.xml        Id, Version, ApiVersion (rules under Hard constraints)
<Id>.xrnx/cover.png           optional renoise.com cover (600x350), with thumbnail.png (120x45)
<Id>.xrnx/main.lua            thin entry: package.path, preferences, APP = require "src.app", APP.start(), dev bridge
<Id>.xrnx/src/app.lua         App.start/stop, App.reg (menu/key/notifier/timer), App.register_dialog, App.guard, App.defer
<Id>.xrnx/src/ui.lua          ViewBuilder dialog; returns (vb, root)
<Id>.xrnx/src/labels.lua      pure Lua (no renoise.*): the dialog's label strings; the unit-tested example
tests/helper.lua              test helpers for tests/*_test.lua
<Id>.xrnx/dev/                dev bridge (bridge.lua, commands.lua, serialize.lua, home_port.lua); never shipped
```

## Hard constraints

- Never hand-edit `definitions/` or `docs/renoise/`; run `just update-defs`
  (it re-applies any local patches, which are listed in `definitions/UPSTREAM.md`).
- `dev/` is development only: `src/` must never `require` anything from `dev.*`,
  and `package` strips it. `tests/` lives outside the bundle and is never shipped.
- The bridge binds `127.0.0.1`. A non-loopback bind (`dev/bind`) requires the token in
  `dev/.token`; `install` writes both on WSL.
- Logic worth unit-testing goes in a pure module (like `src/labels.lua`): no `renoise.*`
  and no Renoise additions to the Lua stdlib (`table.find`, `oprint`, ...), because
  `just test` runs under plain LuaJIT where those do not exist. `src/app.lua` and
  `src/ui.lua` are not testable that way; keep them thin and push logic into pure modules.
  A test is `tests/<name>_test.lua`: `local t = require "tests.helper"`, then `t.eq`,
  `t.check`, `t.fails`, and `t.done()` last (it exits non-zero on failure).
- `main.lua` stays thin and idempotent. Behaviour lives in `src/` behind
  `APP.start()` / `APP.stop()`. No module-level side effects.
- Register menu entries, key bindings, notifiers and timers only through
  `App.reg.*`, and every dialog through `App.register_dialog(name, dialog, vb, root)`.
  That is what makes `reload`, `views` and `dev.view` work.
- Wrap callbacks that Renoise invokes with `App.guard(fn)` so errors reach `just log`.
- Always `require "src.x"` (the `src.` prefix is what the soft reload clears).
- Never `local print = print` at module scope (the bridge hooks the global `print`).
- Never block Renoise's main thread: no `client:receive()`, `client:close()` or
  `server:wait()` inside socket callbacks, no busy loops; long jobs use coroutines
  (see `docs/renoise/guide/`) or `renoise.tool():add_timer`.
- `renoise.song()` can be nil (no song) and changes on load/new; never cache it
  across documents. `App.close_dialogs` runs on `app_new_document_observable`.
- Song list notifiers (`tracks_observable`, `instruments_observable`,
  `sequencer.pattern_sequence_observable`, `phrase_mappings_observable`) fire *during* the edit:
  the list is updated, dependents (pattern tracks, sequence, selection) are not, and they also
  fire on undo/redo. Inside them never edit the song; observe the dependent object if it has an
  observable, else `App.defer(fn)`. Demo: the tracks row in `src/ui.lua`.
- ViewBuilder constructor tables accept only documented fields; a typo such as
  `vb:text { margin = 1 }` crashes at runtime and LuaLS cannot catch it.
- Manifest: `Id` must equal the folder name without `.xrnx`; `Version` is a
  number like `1.02` (`1.0.2` is invalid); `ApiVersion` is `6.2`.

## Conventions

- LuaCATS annotations (`---@param`, `---@return`, `---@class`) on every public
  function and module table; `local` by default; modules return a table.
- Luabind classes are written `class "Name"` (no parentheses; the LuaLS plugin
  only recognises that form), which is why StyLua uses `call_parentheses = "None"`:
  `vb:text { ... }`, `require "src.app"`.
- Prefer `renoise.app():show_status(msg)` over modal dialogs while developing.
- User-visible strings and menu paths live in `src/app.lua` (`App.name`,
  `App.menu_entry`, `App.keybinding`).

## API knowledge

- Reference: `definitions/library/renoise/**/*.lua`. Grep for the class, e.g. `---@class renoise.Song`, `---@class renoise.Views.Button`,
  `function renoise.ScriptingTool:add_menu_entry`. Constructor property tables are the
  `*Properties` classes (`ButtonProperties`, `TextFieldProperties`, ...).
- Renoise's additions to the Lua stdlib are in `definitions/library/standard.lua`:
  `class`, `oprint`, `rprint`, `objinfo`, `ripairs`, `table.create/copy/rcopy/count/find/keys/values/clear/is_empty`,
  `os.platform/currentdir/dirnames/filenames/mkdir/move`, `io.exists/stat/chmod`,
  `math.lin2db/db2lin`, `_AUTO_RELOAD_DEBUG`. `type(obj)` returns the class name for API objects
  (`"Song"`, `"Button"`); `rawequal` compares API objects, `==` does not work on views.
- Guides: `docs/renoise/start/*.md` (tool structure, debugging, distribution) and
  `docs/renoise/guide/*.md` (application, song, document/observables, midi, osc, sockets, sqlite).
  Online: https://renoise.github.io/xrnx/ . Links to `../API/...` in the vendored pages are not
  vendored; use the definitions instead.
- Example tools worth copying patterns from: https://github.com/renoise/xrnx/tree/master/tools
  (`ExampleToolGui` for every ViewBuilder control, `ExampleToolSlicedProcess` for coroutines).
- Known gaps in the definitions (upstream README): `__eq/__lt/__le/__index` metamethods are not
  annotated, and constructors return the class rather than an instance.

## Renoise facts learned while building this kit

- Several tools in development can be installed at once, each with its own bridge. Each bridge
  listens on a **home port** from its tool id (`dev/home_port.lua`; `home_port()` in
  `scripts/renoise.py` must compute the same number, `tests/home_port_test.lua` pins both).
  `renoise.py` pings candidate ports and only uses the one whose `tool_id` matches this project;
  the bridge refuses requests whose `tool` record names another tool. `--port N` skips the check.
  Never "fix" a clash by uninstalling another tool.
- A program started with `os.execute` inherits Renoise's open sockets, including every bridge's
  listening port: while it runs, a reloaded tool cannot bind its port again. Programs a tool
  launches should close inherited descriptors (or be started through the OS shell).
- `print` goes only to Renoise's Scripting Terminal (not Log.txt, not stdout); the bridge
  captures it, so `just eval`/`just log` is the way to read it.
- Relative `require` resolves only while `main.lua` is loading (Renoise's working directory is
  elsewhere in callbacks); `main.lua` prepends `bundle_path` to `package.path` for that reason.
- `renoise.app():install_tool(path)` with a *directory* nests a copy inside an existing install;
  with a `.xrnx` zip it upgrades in place. `renoise.py` always sends a zip.
- The OSC `/renoise/evaluate` endpoint runs in a sandbox (no `io`, `os`, `require`) and never
  replies; it is only used to trigger `install_tool`. All feedback comes through the bridge.
- When a full reload fails to load, Renoise shows an error popup and keeps the old tool instance
  running. The bridge reports the load error for `src/` modules, and `just check` catches syntax
  errors before that.
- `_AUTO_RELOAD_DEBUG = true` makes Renoise reload the tool whenever its window regains focus
  after a file changed, and *opening a dialog counts as regaining focus*. That is why it is off
  in `main.lua` and `just reload` goes through OSC instead.
- A tool's custom dialog is a separate OS window; `just screenshot` captures it as its own PNG.
- Renoise loads tools before it has finished starting. In that phase `renoise.app().theme` and
  `renoise.app().theme_observable` raise "can not access the application theme while the
  application initializes", and the tool fails to load. `just install` and `just reload` run
  on a Renoise that is already up, so they never show it: only a fresh Renoise start does.
  Keep `App.start` to menus, key bindings and `renoise.tool()` observables; register
  `renoise.app()` observables when a dialog first opens (in `App.show_dialog`).

## Git

- Tags `vX.YY` must match `manifest.xml` `<Version>`; pushing one publishes a GitHub release.
- Commit only formatted (`just fmt`) and type-clean code. CI must be green.
- Before tagging, quit Renoise, start it again and check that the tool loads without a
  "Scripting Tool Error".

## Publishing on renoise.com

Read `docs/publishing.md` before uploading to renoise.com, and before changing the bundle's
`README.md`, the manifest `<Description>`, `cover.png` or `thumbnail.png`.
