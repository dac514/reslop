# Setting up a fresh machine

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
     `sudo apt install just luajit`) or the release archive. StyLua and lua-language-server
     come from their GitHub release archives into `~/.local/bin`. For LuaLS, unpack the
     tarball under `~/.local/share/lua-language-server` and symlink `bin/lua-language-server`.
     Make sure `~/.local/bin` is on `PATH`.
3. Rename the placeholder if the user gave a name:
   `just init com.theirname.ToolName "Tool Name" "Their Name [email]"`. The id must be
   reverse-domain style (`com.yourname.ToolName`); ask if you only have a tool name.
4. `just check` and `just test` must pass. Then `just install` (needs Renoise running with its
   OSC server enabled: *Edit > Preferences > OSC > Enable Server*, UDP, port 8000). If the
   bridge does not answer, say exactly which of those is missing instead of guessing.
5. `just ping` and `just song`, then tell the user what you can see (song name, BPM).
