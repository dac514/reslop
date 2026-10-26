# Task runner for this Renoise tool project. Install `just`: https://github.com/casey/just
# Every recipe is a thin wrapper; the same commands work without just.

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

python := if os() == "windows" { "python" } else { "python3" }
rn := python + " scripts/renoise.py"

# List recipes
default:
    @just --list --unsorted

# Check tools, Renoise folders and the dev bridge
doctor:
    {{rn}} doctor

# Format Lua in place
fmt:
    stylua .

# Fail if any Lua file is not formatted
fmt-check:
    stylua --check .

# Type-check the tool with lua-language-server + the vendored Renoise definitions
typecheck:
    lua-language-server --check . --checklevel=Warning --logpath .lls-log --check_format=pretty

# Formatting + types (+ Renoise's own parser when the bridge is reachable)
check: fmt-check typecheck
    -{{rn}} check

# Unit tests: tests/*_test.lua under LuaJIT, no Renoise needed. just test [FILE ...] [-- ARGS]
test *ARGS:
    {{rn}} test {{ARGS}}

# Link (Linux/macOS) or copy (Windows/WSL) the tool into Renoise's Tools folder
install *ARGS:
    {{rn}} install {{ARGS}}

# Remove the tool from Renoise's Tools folder
uninstall:
    {{rn}} uninstall

# Copy mode only: mirror the bundle into the installed copy
sync:
    {{rn}} sync

# Is the dev bridge alive?
ping:
    {{rn}} ping

# Run Lua inside the tool, e.g. just eval 'return renoise.song().transport.bpm' (or eval @file.lua)
eval CODE:
    {{rn}} eval {{quote(CODE)}}

# Full reload: zip the bundle (with dev/) and have Renoise reinstall it via OSC
reload:
    {{rn}} reload

# Quick in-place reload of src/ only (sync, APP.stop, re-require, APP.start)
reload-soft:
    {{rn}} reload --soft

# Dump the view tree of open dialogs
views *ARGS:
    {{rn}} views {{ARGS}}

# Recent prints, errors and bridge messages from inside the tool
log *ARGS:
    {{rn}} log {{ARGS}}

# Summary of the current song
song:
    {{rn}} song

# Screenshot the Renoise window (best effort per OS) into dist/
screenshot *ARGS:
    {{rn}} screenshot {{ARGS}}

# Zip the tool into dist/<Id>.xrnx without dev/
package:
    {{rn}} package

# Rename the template placeholder: just init com.you.Name "Name" ["Your Name [you@example.com]"]
init ID NAME AUTHOR="":
    {{rn}} init --id "{{ID}}" --name "{{NAME}}" --author "{{AUTHOR}}"

# Refresh definitions/ and docs/renoise/ from GitHub
update-defs *ARGS:
    {{rn}} update-defs {{ARGS}}
