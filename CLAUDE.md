# CLAUDE.md

This repository is a **Renoise tool**: an `.xrnx` scripting tool for the
[Renoise](https://www.renoise.com) tracker, written in Lua against the Renoise
Scripting API, plus the tooling to format, type-check, install, reload and
inspect it from the command line while Renoise is running.

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
| `just doctor` | check stylua, lua-language-server, just, Renoise folders, the bridge |
| `just check` | `stylua --check .` + `lua-language-server --check .` (+ Renoise's own parser via the bridge when reachable) |
| `just test` | run `tests/*_test.lua` under plain LuaJIT with the bundle on `package.path`; no Renoise needed. `just test tests/x_test.lua` runs one file, `-- ARGS` go to the test |
| `just fmt` | format all Lua in place |
| `just install` | install into Renoise through OSC `install_tool` (Renoise copies and loads the bundle); falls back to a symlink/copy that needs *Tools > Reload All Tools* once |
| `just reload` | **full reload** (default): zip the bundle (with `dev/`) and `install_tool` it through OSC; fresh Lua state, new `boot_id`, about a second |
| `just reload-soft` | quick in-place reload of `src/` only: sync into the installed copy, `APP.stop()`, drop `src.*` from `package.loaded`, `APP.start()`; keeps the Lua state |
| `just ping` | bridge alive? prints boot_id, bundle path, Renoise/API version |
| `just eval 'CODE'` | run Lua inside the tool's Lua state; `CODE` is an expression or statements; prints captured `print` output and `=> value` per return value |
| `just views` | view tree of every open registered dialog: `Type #id WxH visible text=... value=...` |
| `just log` | last prints, errors, bridge messages from inside the tool (`-n 100`, `--clear`) |
| `just song` | one-screen summary of the current song |
| `just screenshot` | PNGs into `dist/`: on X11/XWayland one file per Renoise window (main window, then each open dialog as `-2`, `-3`...), whole screen elsewhere; then Read the PNGs |
| `just package` | distributable `dist/<Id>.xrnx` without `dev/` |
| `just init com.you.Name "Name" ["You [you@x.com]"]` | rename the template placeholder once |
| `just update-defs` | refresh `definitions/` and `docs/renoise/` from GitHub |

### The development loop

1. Edit `src/*.lua` (behaviour and UI), `main.lua` (entry), `manifest.xml`, or `dev/*` (bridge).
2. `just check`, and `just test` when a pure module or a test changed. Fix everything they report before reloading.
3. `just reload` (full, any file). `just reload-soft` is faster for `src/`-only edits but keeps old
   closures registered outside `App.reg` and does not touch `main.lua`, `manifest.xml` or `dev/`.
4. Verify inside the running Renoise: `just eval 'APP.show_dialog()'`, `just views`,
   `just eval 'dev.set("greeting", "x")'`, `just log`, `just screenshot`. Do not report a GUI
   change as working until `views` (and, for layout, a screenshot) shows it.
5. `just check` again, then commit.

Eval helpers available as the global `dev`: `dev.dialog([name])`, `dev.view(id)`,
`dev.set(id, value)` (assigning `.value` fires the control's notifier, the only way to
"click" programmatically), `dev.log(...)`. `APP` is the application module.

If `renoise.py` exits 3, Renoise is not running or the tool is not installed/loaded
(`just install`). If it exits 4, Renoise is probably stuck on a dialog: take a
screenshot and tell the user instead of retrying blindly. If `reload-soft` reports a
Lua error, the old module stays stopped (menus gone) until a reload succeeds. A full
`reload` that fails to load leaves Renoise showing an error popup and running the old
instance; `just check` catches syntax errors before that happens.

## Setting up a fresh machine

The README tells people to open the project in Claude Code and ask for a setup.
When asked to set the project up, do all of this, in order, and report at the end:

1. `python3 scripts/renoise.py doctor` (`python scripts/renoise.py doctor` on native
   Windows). It lists what is missing with per-OS install hints. Python itself missing?
   macOS and Linux ship it; on Windows `winget install Python.Python.3.13`, or use WSL.
2. Install what is missing. Prefer user-local installs and ask before anything that
   needs `sudo` or an admin shell. Pinned, known-good versions: StyLua 2.6.0,
   lua-language-server 3.19.2 (must be >= 3.13.6), just 1.59.0. LuaJIT 2.1 (any build)
   runs the unit tests; `lua5.1` is accepted as a fallback.
   - macOS: `brew install just stylua lua-language-server luajit` (offer to install Homebrew if absent).
   - Windows: `winget install Casey.Just JohnnyMorganz.StyLua LuaLS.lua-language-server`
     (or `scoop install just stylua lua-language-server`), plus `scoop install luajit`.
   - Linux / WSL: `just` and `luajit` from the distro (`sudo dnf install just luajit`,
     `sudo apt install just luajit`) or the release archive; StyLua and lua-language-server from their GitHub release
     archives into `~/.local/bin` (for LuaLS unpack the tarball under
     `~/.local/share/lua-language-server` and symlink `bin/lua-language-server`).
     Make sure `~/.local/bin` is on `PATH`.
3. Rename the placeholder if the user gave a name:
   `just init com.theirname.ToolName "Tool Name" "Their Name [email]"`. The id must be
   reverse-domain style (`com.yourname.ToolName`); ask if you only have a tool name.
4. `just check` and `just test` must pass. Then `just install` (needs Renoise running with its OSC
   server enabled: *Edit > Preferences > OSC > Enable Server*, UDP, port 8000). If the
   bridge does not answer, say exactly which of those is missing instead of guessing.
5. `just ping` and `just song`, then tell the user what you can see (song name, BPM).

## Directory map

```
CLAUDE.md, README.md          this file; human quick start
justfile                      task runner (python3 on POSIX/WSL, python on Windows)
scripts/renoise.py            CLI: doctor, paths, install, uninstall, sync, ping, eval, reload,
                              views, log, song, check, test, screenshot, package, init, update-defs
.luarc.json                   LuaLS: LuaJIT runtime, definitions as library, class plugin
stylua.toml                   2-space, 100 cols, double quotes, call_parentheses = None
definitions/                  vendored renoise/definitions (LuaCATS); UPSTREAM.md records the commit
docs/renoise/                 vendored xrnx guide pages (start/, guide/)
.github/workflows/ci.yml      stylua --check, lua-language-server --check, unit tests, package
.github/workflows/release.yml tag v* -> GitHub release with the .xrnx attached
<Id>.xrnx/manifest.xml        Id (== folder name), ApiVersion 6.2, Version like 1.02 (no semver)
<Id>.xrnx/main.lua            thin entry: package.path, preferences, APP = require "src.app", APP.start(), dev bridge
<Id>.xrnx/src/app.lua         App.start/stop, App.reg (menu/key/notifier/timer), App.register_dialog, App.guard, App.defer
<Id>.xrnx/src/ui.lua          ViewBuilder dialog; returns (vb, root)
<Id>.xrnx/src/labels.lua      pure Lua (no renoise.*): the dialog's label strings; the unit-tested example
tests/helper.lua              check/eq/fails/done for test files; tests/*_test.lua run under LuaJIT via `just test`
<Id>.xrnx/dev/                dev bridge (bridge.lua, commands.lua, serialize.lua); never shipped
```

## Hard constraints

- Never hand-edit `definitions/` or `docs/renoise/`; run `just update-defs`
  (it re-applies any local patches, which are listed in `definitions/UPSTREAM.md`).
- `dev/` is development only: `src/` must never `require` anything from `dev.*`,
  and `package` strips it. `tests/` lives outside the bundle and is never shipped.
- Logic worth unit-testing goes in a pure module (like `src/labels.lua`): no `renoise.*`
  and no Renoise additions to the Lua stdlib (`table.find`, `oprint`, ...), because
  `just test` runs under plain LuaJIT where those do not exist. `src/app.lua` and
  `src/ui.lua` are not testable that way; keep them thin and push logic into pure modules.
  A test is `tests/<name>_test.lua`: `local t = require "tests.helper"`, then `t.eq`,
  `t.check`, `t.fails`, and `t.done()` last (it exits non-zero on failure). The bridge binds `127.0.0.1`; a non-loopback bind
  (`dev/bind`) requires the token in `dev/.token` (both written by `install` on WSL).
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
- Commit only formatted (`just fmt`) and type-clean code; CI runs both checks.

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

- Reference: `definitions/library/renoise/*.lua` and `definitions/library/renoise/**/*.lua`.
  Grep for the class, e.g. `---@class renoise.Song`, `---@class renoise.Views.Button`,
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
  annotated; constructors return the class rather than an instance; unknown constructor fields
  are not flagged.

## Renoise facts learned while building this kit

- `print` goes only to Renoise's Scripting Terminal (not Log.txt, not stdout); the bridge
  captures it, so `just eval`/`just log` is the way to read it.
- Relative `require` resolves only while `main.lua` is loading (Renoise's working directory is
  elsewhere in callbacks); `main.lua` prepends `bundle_path` to `package.path` for that reason.
- `renoise.app():install_tool(path)` with a *directory* nests a copy inside an existing install;
  with a `.xrnx` zip it upgrades in place. `renoise.py` always sends a zip.
- The OSC `/renoise/evaluate` endpoint runs in a sandbox (no `io`, `os`, `require`) and never
  replies; it is only used to trigger `install_tool`. All feedback comes through the bridge.
- Renoise keeps the old tool instance running when a reload fails to load; the bridge reports
  the load error for `src/` modules, and `just check` catches syntax errors before that.
- `_AUTO_RELOAD_DEBUG = true` makes Renoise reload the tool whenever its window regains focus
  after a file changed, and *opening a dialog counts as regaining focus*. That is why it is off
  in `main.lua` and `just reload` goes through OSC instead.
- A tool's custom dialog is a separate OS window; `just screenshot` captures it as its own PNG.

## Git

- Tags `vX.YY` must match `manifest.xml` `<Version>`; pushing one publishes a GitHub release.
- CI must be green: StyLua, LuaLS, `test` and `package`.
