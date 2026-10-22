# scripts/renoise.py

Standard-library Python 3.8+ CLI used by every `just` recipe. `python3
scripts/renoise.py -h` lists the subcommands; each prints `ok ...` or `error
...` on its first line, payload after it, or one JSON object with `--json`.

| exit | meaning |
|---|---|
| 0 | ok |
| 1 | remote/Lua error, failed reload, refusal |
| 2 | usage |
| 3 | cannot connect to the bridge (Renoise not running / tool not loaded) |
| 4 | timeout (Renoise probably stuck on a dialog) |
| 5 | unsupported on this platform (screenshot, WSL interop) |

Global options: `--bundle`, `--host`, `--port`, `--osc-port`, `--timeout`, `--json`.

## Subcommands

- `doctor`, `paths` — environment and Renoise folder detection.
- `install [--link|--copy] [--loopback] [--force]`, `uninstall`, `sync`.
- `ping`, `eval CODE|-|@file.lua`, `reload [--hard]`, `views [--dialog N] [--all]`,
  `log [-n N] [--clear]`, `song`, `check [--file F]` — bridge requests.
- `screenshot [PATH]`, `package`, `init --id --name [--author]`, `update-defs [--ref] [--xrnx-ref]`.

## Bridge wire format

One request per TCP connection; the client closes after one reply. Both
directions use the same binary-safe framing:

```
<total_len>\n<records>
records := (<name> <len>\n<bytes>)*
```

Request records: `v`=`1`, `kind`, optional `token`, plus per-kind fields
(`code`, `dialog`, `all`, `n`, `clear`, `file`). Replies always carry `status`
(`ok`/`error`), `error` when failed, and per-kind fields (`output`, `result`,
`ms`, `tree`, `count`, `entries`, `summary`, `errors`, `files`, `boot_id`,
`reload_count`, ...). Replies above 1 MiB are cut and flagged `truncated`.
