# Copilot instructions

This repository is a Renoise 3.5 tool written in LuaJIT (Lua 5.1 syntax).
Before changing files, read `CLAUDE.md`; it is the canonical guide to the
project structure, Renoise API, commands, constraints, and development
workflow. Follow it unless these Copilot-specific notes are more precise.

- Tool behavior belongs in the single `*.xrnx/` directory; keep `main.lua`
  thin and put behavior in `src/`.
- Use the vendored Renoise API definitions in `definitions/` and guides in
  `docs/renoise/`; never hand-edit either directory.
- Keep `dev/` development-only; production `src/` must not require `dev.*`.
- Follow the registration, callback guarding, document lifecycle, and
  non-blocking rules in `CLAUDE.md`.
- Run `just check` after Lua changes, and `just test` when a pure module or
  a test changed. Logic worth testing goes in a pure module (no `renoise.*`)
  with a `tests/<name>_test.lua` next to it. For changes that affect a running
  Renoise tool, follow the reload and runtime verification steps in
  `CLAUDE.md`; do not claim runtime or GUI behavior is verified without
  checking it through the bridge.

Do not change unrelated files or weaken existing checks.
