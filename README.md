# ReSlop

Build Renoise tools with a coding assistant doing the typing.

Renoise tools are small Lua scripts (`.xrnx` files) that add menus, dialogs and
new tricks to [Renoise](https://www.renoise.com). ReSlop is a starter kit for
making them. You get a little tool that already works, the complete Renoise API
reference in a form your editor and [Claude Code](https://claude.com/claude-code)
can read, and a bridge that lets Claude run code inside your running Renoise,
look at your dialogs and reload your tool without you lifting a finger.

Yes, the name is a joke. The tools you make with it don't have to be.

Questions or ideas? There is a
[thread on the Renoise forum](https://forum.renoise.com/t/reslop-a-template-to-build-claude-code-tools/79678).

<!-- template:start -->
## Your first tool in five minutes

You need three things: Renoise 3.5 (the demo works), Claude Code, and a GitHub
account. No Lua experience required. No terminal experience required either,
though it never hurts.

1. **Click "Use this template"** at the top of this page and give your
   repository a name. Then get it onto your computer (GitHub Desktop is fine,
   or `git clone`).
2. **Let Renoise listen.** In Renoise, open *Edit → Preferences → OSC* and tick
   *Enable Server*. Keep the defaults (UDP, port 8000). This is how the kit
   installs and reloads your tool without anyone clicking through menus.
3. **Open the folder in Claude Code and ask for a setup.** Something like:

   > Set this project up for me. Install anything that's missing, name the tool
   > com.yourname.ToolName, and check that you can talk to my Renoise.

   Claude installs the formatter, the type checker and the task runner, renames
   the example tool, puts it into Renoise, and reports back when it can see your
   song. If it needs a password for an install, it will ask.
4. **Ask for a feature.** "Add a button that doubles the BPM." "Make a dialog
   that lists every instrument." Claude writes the Lua, checks it against the
   Renoise API, reloads the tool inside Renoise, and shows you the dialog it made.

That is the whole workflow. The rest of this page is for the curious and the
hands-on.
<!-- template:end -->

## What's in the box

```
<Id>.xrnx/            your tool: manifest.xml, main.lua, src/ (logic and dialog), dev/ (the bridge)
scripts/renoise.py    one small Python script that does all the chores below
justfile              short names for the chores, so you can type `just reload`
definitions/          the Renoise API, annotated, for the type checker and for Claude
docs/renoise/         the Renoise scripting guide, offline
CLAUDE.md             the briefing Claude reads before touching anything
.github/workflows/    checks on every push; a release with the .xrnx on every tag
```

The example tool adds *Tools → My Tool...* to Renoise's menu. Its dialog shows
the song name, a live BPM read-out, a track count that follows the song, a text
field that remembers what you type, and a button. It is small on purpose: it
shows the patterns, then gets out of the way.

## Doing it by hand

If you would rather type the commands yourself, this is what the setup prompt
does for you.

Install four things: [just](https://github.com/casey/just) (runs the chores),
[StyLua](https://github.com/JohnnyMorganz/StyLua) (formats Lua),
[lua-language-server](https://github.com/LuaLS/lua-language-server) 3.13.6 or
newer (checks Lua against the Renoise API), and Python 3.8 or newer (runs the
script; no packages needed).

- macOS: `brew install just stylua lua-language-server`
- Windows: `winget install Casey.Just JohnnyMorganz.StyLua LuaLS.lua-language-server Python.Python.3.13`
  (or work inside WSL and follow the Linux line)
- Fedora, Ubuntu, WSL: `just` from your package manager, StyLua and
  lua-language-server from their GitHub release archives, unpacked into `~/.local/bin`

Then:

```
just doctor      # lists what is missing and where to get it
just init com.yourname.ToolName "Tool Name" "Your Name [you@example.com]"
just install     # Renoise copies the tool into its Tools folder and loads it
just ping        # ok bridge at 127.0.0.1:18765 ...
```

No `just` yet? Every recipe is a one-liner around the script, so
`python3 scripts/renoise.py doctor` works just as well.

## Day to day

```
just check          # formatting + type check against the Renoise API
just reload         # full reload: zip the tool and have Renoise reinstall it (about a second)
just reload-soft    # quicker: swap in src/ without restarting the tool
just eval 'return renoise.song().transport.bpm'
just eval 'APP.show_dialog()' && just views
just log            # prints and errors from inside the tool
just screenshot     # PNG of the Renoise window and any open dialog, into dist/
just package        # dist/<Id>.xrnx, ready to share (the dev bridge is left out)
```

## How Claude sees Renoise

Renoise has no command line, and `print` only reaches its Scripting Terminal.
So the kit ships a small **dev bridge** inside the tool (`dev/bridge.lua`): a
TCP server on `127.0.0.1:18765`, living in the tool's own Lua state, loaded
only while `dev/` exists and never included by `just package`. The script talks
to it:

- `eval` runs Lua with full access to the tool (`APP`, `renoise`, `io`), captures
  `print` output and returns values as text.
- `views` walks the dialog tree of every registered dialog, so layout and
  state can be verified without a screenshot.
- `reload` re-zips the tool and asks Renoise to reinstall it through the OSC
  server, giving a fresh Lua state in about a second; `reload --soft` swaps in
  `src/` in place instead.
- `log` keeps the last 500 prints and errors; `check` parses the sources with
  Renoise's own LuaJIT.

Renoise's OSC server is used only as a trigger (`/renoise/evaluate` →
`renoise.app():install_tool(zip)`), because it cannot send anything back.
Screenshots are best effort per OS: on X11 every Renoise window is captured,
so an open tool dialog lands in its own PNG; elsewhere you get the whole screen
(`spectacle`, `gnome-screenshot`, `grim`, `screencapture`, PowerShell).

## Platform notes

| | Linux | macOS | Windows (native) | WSL (Linux tools, Windows Renoise) |
|---|---|---|---|---|
| Tools folder | `~/.config/Renoise/V*/Scripts/Tools` | `~/Library/Preferences/Renoise/V*/Scripts/Tools` | `%APPDATA%\Renoise\V*\Scripts\Tools` | found via `powershell.exe $env:APPDATA` |
| `just install` | OSC, else symlink | OSC, else symlink | OSC, else copy (`--link` = junction) | OSC, else copy |
| Bridge bind | 127.0.0.1 | 127.0.0.1 | 127.0.0.1 | `0.0.0.0` + token (NAT mode cannot reach the host's loopback) |
| Screenshot | window or screen | screen | screen | screen via `powershell.exe` |

WSL: `just install` writes `dev/bind` (`0.0.0.0`) and `dev/.token` so the bridge
is reachable from the WSL network namespace and still refuses unauthenticated
peers; the client tries `127.0.0.1`, the default gateway and the resolv.conf
nameserver as hosts. With mirrored networking (`.wslconfig`), pass
`--loopback` to keep everything on localhost. Paths handed to Renoise are
converted with `wslpath -w`.

Environment overrides: `RENOISE_PREFS_DIR`, `RENOISE_VERSION`, `RENOISE_HOST`,
`RENOISE_DEV_PORT`, `RENOISE_OSC_PORT`.

## Credits and license

MIT. Bundles the MIT-licensed
[renoise/definitions](https://github.com/renoise/definitions) and guide pages from
[renoise/xrnx](https://github.com/renoise/xrnx); see the `UPSTREAM.md` files for
the exact commits.
