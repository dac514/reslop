#!/usr/bin/env python3
"""Dev helper for Renoise tool projects. Python 3.8+, standard library only.

Talks to the dev bridge (dev/bridge.lua) inside the running Renoise, installs
the tool into Renoise's Tools folder, packages it, runs the LuaJIT unit tests
in tests/, and more. Run with -h.

Output contract: the first line is `ok ...` or `error <reason>`; everything
after it is payload. Pass --json for a single JSON object instead.

Exit codes: 0 ok | 1 remote error or refusal | 2 usage | 3 cannot connect
| 4 timeout | 5 unsupported on this platform
"""

import argparse
import datetime as _dt
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 18765
DEFAULT_OSC_PORT = 8000
DEFAULT_TIMEOUT = 10.0

EXIT_OK, EXIT_REMOTE, EXIT_USAGE, EXIT_CONNECT, EXIT_TIMEOUT, EXIT_UNSUPPORTED = 0, 1, 2, 3, 4, 5

PLACEHOLDER_ID = "com.example.MyTool"
PLACEHOLDER_NAME = "My Tool"
PLACEHOLDER_AUTHOR = "Example Author [author@example.com]"

SYNC_KEEP = {"preferences.xml", "dev/.port"}
SKIP_NAMES = {".git", "__pycache__", ".DS_Store", "Thumbs.db"}
PACKAGE_EXCLUDE_DIRS = {"dev"}
PACKAGE_EXCLUDE_FILES = {"preferences.xml"}

MIN_LUALS = (3, 13, 6)

# Fixes applied on top of the vendored renoise/definitions, re-applied by `update-defs` and
# listed in definitions/UPSTREAM.md. Each entry is (relative path, old text, new text, why).
# Send fixes upstream and drop them here once merged; the last one, a missing
# `---@return string` on `tostring(note_column)`, landed as renoise/definitions#48.
DEFINITION_PATCHES = []


class Fail(Exception):
    def __init__(self, reason, code=EXIT_REMOTE, payload=""):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.payload = payload


# --------------------------------------------------------------------------
# Platform


def detect_platform():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if os.environ.get("WSL_DISTRO_NAME"):
        return "wsl"
    try:
        if "microsoft" in Path("/proc/version").read_text().lower():
            return "wsl"
    except OSError:
        pass
    return "linux"


PLATFORM = detect_platform()


def run(cmd, timeout=15, check=False, **kw):
    """Run a command, returning CompletedProcess; never raises on nonzero."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check, **kw)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", "command not found: %s" % cmd[0])
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timeout: %s" % " ".join(map(str, cmd)))


def which(name):
    return shutil.which(name)


def wslpath(path, to_windows=False):
    flag = "-w" if to_windows else "-u"
    r = run(["wslpath", flag, str(path)])
    if r.returncode != 0:
        raise Fail("wslpath failed: %s" % r.stderr.strip(), EXIT_UNSUPPORTED)
    return r.stdout.strip()


def powershell(script, timeout=30):
    exe = "powershell.exe" if PLATFORM == "wsl" else "powershell"
    if not which(exe):
        raise Fail("%s not found (WSL interop disabled?)" % exe, EXIT_UNSUPPORTED)
    return run([exe, "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout)


# --------------------------------------------------------------------------
# Renoise locations


def prefs_root():
    override = os.environ.get("RENOISE_PREFS_DIR")
    if override:
        return Path(override)
    if PLATFORM == "linux":
        return Path.home() / ".config" / "Renoise"
    if PLATFORM == "macos":
        return Path.home() / "Library" / "Preferences" / "Renoise"
    if PLATFORM == "windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise Fail("APPDATA is not set", EXIT_UNSUPPORTED)
        return Path(appdata) / "Renoise"
    # WSL: ask Windows where APPDATA is, fall back to scanning /mnt/c/Users.
    try:
        r = powershell("$env:APPDATA")
        if r.returncode == 0 and r.stdout.strip():
            return Path(wslpath(r.stdout.strip())) / "Renoise"
    except Fail:
        pass
    candidates = list(Path("/mnt/c/Users").glob("*/AppData/Roaming/Renoise"))
    if len(candidates) == 1:
        return candidates[0]
    raise Fail(
        "cannot locate the Windows Renoise preferences folder from WSL; "
        "set RENOISE_PREFS_DIR=/mnt/c/Users/<you>/AppData/Roaming/Renoise",
        EXIT_UNSUPPORTED,
    )


def version_tuple(name):
    m = re.fullmatch(r"V(\d+)\.(\d+)(?:\.(\d+))?", name)
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def renoise_version_dir():
    root = prefs_root()
    if not root.is_dir():
        raise Fail("Renoise preferences folder not found: %s (start Renoise once)" % root, EXIT_CONNECT)
    wanted = os.environ.get("RENOISE_VERSION")
    if wanted:
        d = root / ("V" + wanted.lstrip("Vv"))
        if not d.is_dir():
            raise Fail("no such Renoise version folder: %s" % d, EXIT_USAGE)
        return d
    dirs = [(version_tuple(d.name), d) for d in root.iterdir() if d.is_dir() and version_tuple(d.name)]
    if not dirs:
        raise Fail("no V*.*.* folder inside %s" % root, EXIT_CONNECT)
    return max(dirs)[1]


def tools_dir():
    return renoise_version_dir() / "Scripts" / "Tools"


# --------------------------------------------------------------------------
# Bundle


def find_bundle(explicit=None):
    if explicit:
        p = Path(explicit).resolve()
        if not p.is_dir():
            raise Fail("bundle not found: %s" % p, EXIT_USAGE)
        return p
    found = [p for p in ROOT.iterdir() if p.is_dir() and p.name.endswith(".xrnx")]
    if len(found) != 1:
        raise Fail("expected exactly one *.xrnx folder in %s, found %d" % (ROOT, len(found)), EXIT_USAGE)
    return found[0]


def manifest(bundle):
    import xml.etree.ElementTree as ET

    path = bundle / "manifest.xml"
    if not path.is_file():
        raise Fail("missing %s" % path, EXIT_USAGE)
    tree = ET.parse(path)
    get = lambda tag: (tree.findtext(tag) or "").strip()
    info = {"Id": get("Id"), "Version": get("Version"), "Name": get("Name"), "ApiVersion": get("ApiVersion")}
    if info["Id"] + ".xrnx" != bundle.name:
        raise Fail("manifest Id '%s' does not match folder name '%s'" % (info["Id"], bundle.name), EXIT_USAGE)
    return info


def install_target(bundle):
    return tools_dir() / bundle.name


def is_link(path):
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            return bool(os.stat(path, follow_symlinks=False).st_file_attributes & 0x400)  # reparse point
        except OSError:
            return False
    return False


def install_state(bundle):
    """Return (state, target): state in {'absent','link','copy','foreign'}.

    'copy' is any real folder whose manifest Id matches ours: one made by
    `sync`, or by Renoise itself when `install_tool` copied the bundle.
    """
    target = install_target(bundle)
    if not target.exists() and not target.is_symlink():
        return "absent", target
    if is_link(target):
        return "link", target
    try:
        if manifest(target)["Id"] == manifest(bundle)["Id"]:
            return "copy", target
    except Fail:
        pass
    return "foreign", target


def installed_bundle(bundle):
    state, target = install_state(bundle)
    return target if state in ("link", "copy") else bundle


# --------------------------------------------------------------------------
# Bridge protocol


def encode(records):
    body = b"".join(
        ("%s %d\n" % (k, len(v.encode()))).encode() + v.encode() for k, v in records.items() if v is not None
    )
    return ("%d\n" % len(body)).encode() + body


def decode(frame):
    records = {}
    pos = 0
    while pos < len(frame):
        nl = frame.index(b"\n", pos)
        name, length = frame[pos:nl].decode().split(" ")
        length = int(length)
        records[name] = frame[nl + 1 : nl + 1 + length].decode("utf-8", "replace")
        pos = nl + 1 + length
    return records


def read_port(bundle):
    for candidate in (installed_bundle(bundle) / "dev" / ".port", bundle / "dev" / "port"):
        try:
            first = candidate.read_text().splitlines()[0].strip()
            if first.isdigit():
                return int(first)
        except (OSError, IndexError):
            continue
    return DEFAULT_PORT


def read_token(bundle):
    try:
        return (bundle / "dev" / ".token").read_text().strip() or None
    except OSError:
        return None


def host_candidates(explicit=None):
    if explicit:
        return [explicit]
    env = os.environ.get("RENOISE_HOST")
    if env:
        return [env]
    hosts = ["127.0.0.1"]
    if PLATFORM == "wsl":
        r = run(["ip", "route", "show", "default"])
        m = re.search(r"via (\S+)", r.stdout)
        if m:
            hosts.append(m.group(1))
        try:
            for line in Path("/etc/resolv.conf").read_text().splitlines():
                if line.startswith("nameserver"):
                    hosts.append(line.split()[1])
        except OSError:
            pass
    seen, out = set(), []
    for h in hosts:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def connect(args, bundle, retry_seconds=3.0):
    """Open a connection to the bridge. A refused connection is retried for a few
    seconds, because Renoise restarts the bridge whenever it reloads the tool
    (e.g. _AUTO_RELOAD_DEBUG firing when Renoise regains focus after a sync)."""
    port = args.port or (int(os.environ["RENOISE_DEV_PORT"]) if os.environ.get("RENOISE_DEV_PORT") else None) or read_port(bundle)
    deadline = time.time() + retry_seconds
    while True:
        errors = []
        for host in host_candidates(args.host):
            try:
                s = socket.create_connection((host, port), timeout=1.5)
                s.settimeout(args.timeout)
                return s, host, port
            except OSError as e:
                errors.append("%s:%d (%s)" % (host, port, e))
        if time.time() >= deadline:
            break
        time.sleep(0.3)
    raise Fail(
        "cannot connect to the dev bridge: %s. Is Renoise running with the tool installed and loaded? "
        "Try: just install, then Tools > Reload All Tools in Renoise." % "; ".join(errors),
        EXIT_CONNECT,
    )


def request(args, bundle, kind, _retry=3.0, **records):
    records = {"v": "1", "kind": kind, **{k: v for k, v in records.items() if v is not None}}
    token = read_token(bundle)
    if token:
        records["token"] = token
    s, host, port = connect(args, bundle, retry_seconds=_retry)
    try:
        s.sendall(encode(records))
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                raise Fail("bridge closed the connection without replying (token rejected?)", EXIT_REMOTE)
            buf += chunk
        nl = buf.index(b"\n")
        total = int(buf[:nl])
        body = buf[nl + 1 :]
        while len(body) < total:
            chunk = s.recv(65536)
            if not chunk:
                raise Fail("connection closed mid-reply", EXIT_REMOTE)
            body += chunk
    except socket.timeout:
        raise Fail(
            "timeout: no reply from the bridge in %.0fs. Renoise is probably showing a modal dialog or an "
            "error popup; close it (or take a screenshot to see it) and retry." % args.timeout,
            EXIT_TIMEOUT,
        )
    finally:
        s.close()
    reply = decode(body[:total])
    reply["_host"], reply["_port"] = host, str(port)
    return reply


# --------------------------------------------------------------------------
# OSC (fire-and-forget; Renoise's OSC server must be enabled in Preferences)


def osc_str(x):
    b = x.encode() + b"\0"
    return b + b"\0" * (-len(b) % 4)


def osc_evaluate(args, code):
    """Send `code` to /renoise/evaluate on every host candidate. No reply exists."""
    port = args.osc_port or int(os.environ.get("RENOISE_OSC_PORT", DEFAULT_OSC_PORT))
    pkt = osc_str("/renoise/evaluate") + osc_str(",s") + osc_str(code)
    sent = []
    for host in host_candidates(args.host):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(pkt, (host, port))
            sent.append("%s:%d" % (host, port))
        except OSError:
            continue
    return sent


def renoise_path(path):
    """The path as Renoise (possibly on the Windows side of WSL) must see it."""
    return wslpath(path, to_windows=True) if PLATFORM == "wsl" else str(path)


def dev_package(bundle):
    """Zip the bundle *including dev/* into dist/.dev/<Id>.xrnx for install_tool.

    Renoise's install_tool takes an .xrnx zip (the same path its own tool
    updater uses). Passing a directory works for a first install but nests a
    copy inside the existing folder on upgrade, so always hand it a zip.
    """
    info = manifest(bundle)
    out_dir = ROOT / "dist" / ".dev"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (info["Id"] + ".xrnx")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in iter_bundle_files(bundle, (), {"preferences.xml", "dev/.port"}):
            z.write(bundle / rel, rel.as_posix())
    return out


def osc_install_tool(args, bundle):
    """Ask Renoise to (re)install the bundle (zipped with dev/). Returns the OSC targets."""
    lua = "renoise.app():install_tool([==[%s]==])" % renoise_path(dev_package(bundle))
    return osc_evaluate(args, lua)


def wait_for_boot(args, bundle, previous_boot, seconds):
    """Poll ping until the bridge reports a boot_id different from `previous_boot`."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(0.3)
        try:
            reply = request(args, bundle, "ping", _retry=0.0)
        except Fail:
            continue
        if reply.get("boot_id") != previous_boot:
            return reply
    return None


def current_boot(args, bundle):
    try:
        return request(args, bundle, "ping", _retry=0.0).get("boot_id")
    except Fail:
        return None


# --------------------------------------------------------------------------
# Output helpers


def emit(args, reply, headline, body=""):
    """Print a reply. Returns the exit code."""
    status = reply.get("status", "ok")
    if args.json:
        print(json.dumps(reply, ensure_ascii=False))
        return EXIT_OK if status == "ok" else EXIT_REMOTE
    if status == "ok":
        print("ok" + (" " + headline if headline else ""))
    else:
        print("error " + reply.get("error", "unknown").splitlines()[0])
    if body:
        print(body)
    if reply.get("truncated") == "1":
        print("[reply truncated at 1 MiB]")
    return EXIT_OK if status == "ok" else EXIT_REMOTE


def section(label, text):
    return "%s\n%s" % (label, text) if text else ""


# --------------------------------------------------------------------------
# Commands: bridge


def cmd_ping(args):
    bundle = find_bundle(args.bundle)
    reply = request(args, bundle, "ping")
    lines = "\n".join("%s=%s" % (k, v) for k, v in sorted(reply.items()) if k != "status")
    return emit(args, reply, "bridge at %s:%s" % (reply["_host"], reply["_port"]), lines)


def read_code(arg):
    if arg == "-":
        return sys.stdin.read()
    if arg.startswith("@"):
        return Path(arg[1:]).read_text()
    return arg


def cmd_eval(args):
    bundle = find_bundle(args.bundle)
    reply = request(args, bundle, "eval", code=read_code(args.code))
    parts = []
    if reply.get("output"):
        parts.append(reply["output"])
    if reply.get("status") == "ok":
        if reply.get("result"):
            parts.append("=> " + reply["result"].replace("\n", "\n   "))
    elif "\n" in reply.get("error", ""):
        parts.append(reply["error"])  # traceback; the first line is already the headline
    return emit(args, reply, "%sms" % reply.get("ms", "?"), "\n".join(parts))


def cmd_reload(args):
    bundle = find_bundle(args.bundle)
    if not args.soft:
        return hard_reload(args, bundle)
    state, target = install_state(bundle)
    if state == "copy":
        n = sync_tree(bundle, target)
        print("synced %d file(s) to %s" % (n, target))
    reply = request(args, bundle, "reload")
    body = reply.get("output", "")
    if reply.get("status") != "ok" and "\n" in reply.get("error", ""):
        body = "\n".join(x for x in (body, reply["error"]) if x)
    return emit(args, reply, "soft reload #%s (src/ re-required; main.lua, manifest.xml and dev/ untouched)" % reply.get("reload_count", "?"), body)


def focus_renoise():
    """Best-effort: bring the Renoise window to the front. Returns a description or None."""
    if PLATFORM in ("windows", "wsl"):
        r = powershell("(New-Object -ComObject WScript.Shell).AppActivate('Renoise')")
        return "powershell AppActivate" if r.returncode == 0 and "True" in r.stdout else None
    if PLATFORM == "macos":
        r = run(["osascript", "-e", 'tell application "Renoise" to activate'])
        return "osascript activate" if r.returncode == 0 else None
    if which("xdotool"):
        r = run(["xdotool", "search", "--class", "renoise", "windowactivate", "--sync"])
        if r.returncode == 0:
            return "xdotool windowactivate"
    if which("wmctrl"):
        r = run(["wmctrl", "-x", "-a", "renoise"])
        if r.returncode == 0:
            return "wmctrl -a"
    return None


def hard_reload(args, bundle):
    """Full reload of the whole tool (main.lua, manifest.xml, dev/ included).

    1. OSC: `renoise.app():install_tool(<zip of the bundle>)` makes Renoise copy
       the bundle into its Tools folder again and reload it. No window focus needed.
    2. Fallback: touch main.lua and focus Renoise, which only helps when the tool
       sets `_AUTO_RELOAD_DEBUG = true`.
    """
    before = current_boot(args, bundle)
    targets = osc_install_tool(args, bundle)
    after = wait_for_boot(args, bundle, before, max(args.timeout, 10))
    if after:
        return emit(args, after, "hard reload via OSC install_tool: boot %s -> %s" % (before, after["boot_id"]))
    os.utime(bundle / "main.lua", None)
    how = focus_renoise()
    if how:
        after = wait_for_boot(args, bundle, before, max(args.timeout, 15))
        if after:
            return emit(args, after, "hard reload via %s: boot %s -> %s" % (how, before, after["boot_id"]))
    raise Fail(
        "reload did not take (boot_id still %s). OSC was sent to %s; make sure the OSC server is enabled in "
        "Renoise > Preferences > OSC (UDP, port %s). Otherwise use Tools > Reload All Tools in Renoise (or set "
        "_AUTO_RELOAD_DEBUG = true in main.lua so focusing Renoise reloads). If the new main.lua failed to load, "
        "Renoise shows an error popup and keeps the old instance (run `check`)."
        % (before, ", ".join(targets) or "nowhere", args.osc_port or os.environ.get("RENOISE_OSC_PORT", DEFAULT_OSC_PORT)),
        EXIT_REMOTE,
    )


def cmd_views(args):
    bundle = find_bundle(args.bundle)
    reply = request(args, bundle, "views", dialog=args.dialog, all="1" if args.all else None)
    return emit(args, reply, "%s dialog(s)" % reply.get("count", "?"), reply.get("tree", ""))


def cmd_log(args):
    bundle = find_bundle(args.bundle)
    reply = request(args, bundle, "log", n=str(args.n), clear="1" if args.clear else None)
    return emit(args, reply, "%s entries" % reply.get("count", "?"), reply.get("entries", ""))


def cmd_song(args):
    bundle = find_bundle(args.bundle)
    reply = request(args, bundle, "song")
    return emit(args, reply, "", reply.get("summary", ""))


def cmd_check(args):
    bundle = find_bundle(args.bundle)
    reply = request(args, bundle, "check", file=args.file)
    return emit(args, reply, "%s file(s) parsed by Renoise" % reply.get("files", "?"), reply.get("errors", ""))


# --------------------------------------------------------------------------
# Commands: test

TESTS_DIR = ROOT / "tests"
TEST_GLOB = "*_test.lua"
LUA_INTERPRETERS = ("luajit", "lua5.1", "lua51")


def find_lua():
    """Name of the first Lua 5.1 interpreter on PATH (LuaJIT preferred), or None."""
    for name in LUA_INTERPRETERS:
        if which(name):
            return name
    return None


def cmd_test(args):
    """Run tests/*_test.lua under LuaJIT with the bundle on package.path (no Renoise needed)."""
    bundle = find_bundle(args.bundle)
    lua = find_lua()
    if not lua:
        raise Fail("no Lua interpreter found (tried %s): %s" % (", ".join(LUA_INTERPRETERS), INSTALL_HINTS["luajit"][PLATFORM]), EXIT_USAGE)
    rest = list(args.rest)
    extra = []
    if "--" in rest:
        i = rest.index("--")
        rest, extra = rest[:i], rest[i + 1 :]
    if rest:
        files = [Path(f).resolve() for f in rest]
        missing = [str(f) for f in files if not f.is_file()]
        if missing:
            raise Fail("no such test file: %s" % ", ".join(missing), EXIT_USAGE)
    else:
        files = sorted(TESTS_DIR.glob(TEST_GLOB)) if TESTS_DIR.is_dir() else []
        if not files:
            raise Fail("no tests found: add tests/%s (see tests/helper.lua)" % TEST_GLOB, EXIT_USAGE)
    # `require "src.x"` resolves against the bundle like inside Renoise; `require "tests.helper"` against the repo root.
    env = dict(os.environ)
    env["LUA_PATH"] = ";".join([str(bundle / "?.lua"), str(bundle / "?" / "init.lua"), str(ROOT / "?.lua"), ""]) + ";"
    env["XRNX_BUNDLE"] = str(bundle)
    results = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix() if ROOT in f.parents else str(f)
        r = subprocess.run([lua, str(f)] + extra, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output = r.stdout.rstrip()
        results.append({"file": rel, "ok": r.returncode == 0, "exit": r.returncode, "output": output})
        if not args.json:
            print("%s %s" % ("PASS" if r.returncode == 0 else "FAIL", rel))
            if output:
                print("\n".join("  " + line for line in output.splitlines()))
    failed = [x for x in results if not x["ok"]]
    if args.json:
        print(json.dumps({"status": "ok" if not failed else "error", "lua": lua, "files": results}))
    elif failed:
        print("error %d of %d test file(s) failed (%s)" % (len(failed), len(results), lua))
    else:
        print("ok %d test file(s) passed (%s)" % (len(results), lua))
    return EXIT_OK if not failed else EXIT_REMOTE


# --------------------------------------------------------------------------
# Commands: install / sync / package


def iter_bundle_files(bundle, exclude_dirs=(), exclude_files=()):
    for dirpath, dirnames, filenames in os.walk(bundle):
        rel_dir = Path(dirpath).relative_to(bundle)
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_NAMES and str(rel_dir / d) not in exclude_dirs
        )
        for f in sorted(filenames):
            rel = rel_dir / f
            if f in SKIP_NAMES or str(rel) in exclude_files or rel.as_posix() in exclude_files:
                continue
            yield rel


def sync_tree(src, dst):
    """Mirror src into dst, keeping Renoise's runtime files. Returns files copied."""
    dst.mkdir(parents=True, exist_ok=True)
    wanted = set()
    copied = 0
    for rel in iter_bundle_files(src):
        wanted.add(rel.as_posix())
        s, d = src / rel, dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if not d.exists() or s.stat().st_size != d.stat().st_size or int(s.stat().st_mtime) > int(d.stat().st_mtime):
            shutil.copy2(s, d)
            copied += 1
    for dirpath, dirnames, filenames in os.walk(dst, topdown=False):
        rel_dir = Path(dirpath).relative_to(dst)
        for f in filenames:
            rel = (rel_dir / f).as_posix()
            if rel not in wanted and rel not in SYNC_KEEP:
                (dst / rel).unlink()
        for d in dirnames:
            p = dst / rel_dir / d
            if not any(p.iterdir()):
                p.rmdir()
    return copied


def make_link(src, dst):
    if os.name == "nt":
        try:
            os.symlink(src, dst, target_is_directory=True)
            return "symlink"
        except OSError:
            r = run(["cmd", "/c", "mklink", "/J", str(dst), str(src)])
            if r.returncode != 0:
                raise Fail("mklink /J failed: %s" % (r.stderr or r.stdout).strip(), EXIT_REMOTE)
            return "junction"
    os.symlink(src, dst, target_is_directory=True)
    return "symlink"


def ensure_wsl_bridge_config(bundle):
    """WSL (NAT mode) cannot reach the Windows host's loopback, so the bridge
    must listen on all interfaces and require a token."""
    dev = bundle / "dev"
    if not dev.is_dir():
        return []
    notes = []
    bind = dev / "bind"
    if not bind.exists():
        bind.write_text("0.0.0.0\n")
        notes.append("wrote dev/bind = 0.0.0.0 (so WSL can reach the bridge; remove it if you use mirrored networking)")
    token = dev / ".token"
    if not token.exists():
        token.write_text(secrets.token_hex(16) + "\n")
        notes.append("wrote dev/.token (required by the bridge when bound beyond loopback)")
    return notes


def cmd_install(args):
    bundle = find_bundle(args.bundle)
    manifest(bundle)
    notes = []
    if PLATFORM == "wsl" and not args.loopback:
        notes += ensure_wsl_bridge_config(bundle)
    state, target = install_state(bundle)
    if state == "foreign" and not args.force:
        raise Fail("a different tool already lives at %s (manifest Id mismatch); remove it or pass --force" % target)

    # Preferred: let Renoise copy and load the bundle itself (needs the OSC server).
    if not args.link and not args.copy and state != "link":
        before = current_boot(args, bundle)
        targets = osc_install_tool(args, bundle)
        after = wait_for_boot(args, bundle, before, max(args.timeout, 10))
        if after:
            print("ok installed via OSC install_tool; Renoise copied the bundle to %s and loaded it" % after.get("bundle_path"))
            print("bridge at %s:%s (boot %s)" % (after["_host"], after["_port"], after["boot_id"]))
            for n in notes:
                print(n)
            print("edits: `reload` reinstalls everything the same way; `reload --soft` syncs src/ and re-requires it in place")
            return EXIT_OK
        print("OSC install_tool got no answer from the bridge (sent to %s); falling back to a %s"
              % (", ".join(targets) or "nowhere", "link" if PLATFORM in ("linux", "macos") else "copy"))

    mode = "link" if args.link else "copy" if args.copy else ("link" if PLATFORM in ("linux", "macos") else "copy")
    if state == "link":
        if mode == "link":
            print("ok already installed as a link: %s -> %s" % (target, os.path.realpath(target)))
            return EXIT_OK
        os.unlink(target) if not os.name == "nt" else os.rmdir(target)
        state = "absent"
    if state in ("copy", "foreign") and mode == "link":
        shutil.rmtree(target)
        state = "absent"
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "link":
        how = make_link(bundle, target)
        print("ok installed as %s: %s -> %s" % (how, target, bundle))
    else:
        n = sync_tree(bundle, target)
        print("ok installed as copy (%d files): %s" % (n, target))
        print("edits are mirrored on every `reload`; or run `sync` by hand")
    for n in notes:
        print(n)
    print("next: in Renoise choose Tools > Reload All Tools (or enable the OSC server so this step is automatic), then `ping`")
    return EXIT_OK


def cmd_uninstall(args):
    bundle = find_bundle(args.bundle)
    state, target = install_state(bundle)
    if state == "absent":
        print("ok nothing installed at %s" % target)
        return EXIT_OK
    if state == "link":
        os.rmdir(target) if os.name == "nt" else os.unlink(target)
    elif state == "copy":
        shutil.rmtree(target)
    else:
        raise Fail("%s was not installed by this script; remove it by hand" % target)
    print("ok removed %s" % target)
    return EXIT_OK


def cmd_sync(args):
    bundle = find_bundle(args.bundle)
    state, target = install_state(bundle)
    if state == "link":
        print("ok installed as a link; nothing to sync")
        return EXIT_OK
    if state != "copy":
        raise Fail("not installed in copy mode (state: %s); run `install` first" % state)
    n = sync_tree(bundle, target)
    print("ok synced %d file(s) to %s" % (n, target))
    return EXIT_OK


def cmd_paths(args):
    bundle = find_bundle(args.bundle)
    info = {"platform": PLATFORM, "bundle": str(bundle)}
    try:
        info["prefs_dir"] = str(prefs_root())
        info["renoise_version_dir"] = str(renoise_version_dir())
        info["tools_dir"] = str(tools_dir())
        state, target = install_state(bundle)
        info["install_target"] = str(target)
        info["installed"] = state
    except Fail as e:
        info["error"] = e.reason
    info["bridge_hosts"] = ",".join(host_candidates(args.host))
    info["bridge_port"] = str(args.port or read_port(bundle))
    info["osc_port"] = str(args.osc_port or os.environ.get("RENOISE_OSC_PORT", DEFAULT_OSC_PORT))
    if PLATFORM == "wsl":
        info["bundle_as_seen_by_renoise"] = renoise_path(bundle)
    if args.json:
        print(json.dumps(info))
    else:
        print("ok")
        for k, v in info.items():
            print("%s=%s" % (k, v))
    return EXIT_OK


def cmd_package(args):
    bundle = find_bundle(args.bundle)
    info = manifest(bundle)
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / (info["Id"] + ".xrnx")
    files = list(iter_bundle_files(bundle, PACKAGE_EXCLUDE_DIRS, PACKAGE_EXCLUDE_FILES))
    files = [f for f in files if not f.name.startswith(".")]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            z.write(bundle / rel, rel.as_posix())
        if not (bundle / "LICENSE").exists() and (ROOT / "LICENSE").exists():
            z.write(ROOT / "LICENSE", "LICENSE")
            files.append(Path("LICENSE"))
    print("ok %s (%d files, version %s)" % (out, len(files), info["Version"]))
    for rel in files:
        print("  " + rel.as_posix())
    return EXIT_OK


# --------------------------------------------------------------------------
# Commands: screenshot


PS_SCREENSHOT = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$null = (New-Object -ComObject WScript.Shell).AppActivate('Renoise')
Start-Sleep -Milliseconds 400
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$bmp.Save('%s', [System.Drawing.Imaging.ImageFormat]::Png)
"""


def x11_renoise_windows():
    """All X11 windows whose WM_CLASS mentions renoise: the main window first,
    then dialogs (custom tool dialogs and error popups are separate windows)."""
    r = run(["xprop", "-root", "_NET_CLIENT_LIST"])
    if r.returncode != 0:
        return []
    found = []
    for wid in re.findall(r"0x[0-9a-f]+", r.stdout):
        c = run(["xprop", "-id", wid, "WM_CLASS", "WM_NAME"])
        if "renoise" in c.stdout.lower():
            m = re.search(r'WM_NAME\(\w+\) = "(.*)"', c.stdout)
            found.append((wid, m.group(1) if m else "?"))
    return found


def cmd_screenshot(args):
    out = Path(args.path) if args.path else ROOT / "dist" / ("screenshot-%s.png" % _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out = out.resolve()
    tried = []

    def attempt(label, cmd, **kw):
        tried.append(label)
        r = run(cmd, timeout=30, **kw)
        return r.returncode == 0 and out.is_file() and out.stat().st_size > 0

    done = None
    if PLATFORM in ("windows", "wsl"):
        win_path = wslpath(out, to_windows=True) if PLATFORM == "wsl" else str(out)
        tried.append("powershell CopyFromScreen")
        r = powershell(PS_SCREENSHOT % win_path.replace("'", "''"))
        if r.returncode == 0 and out.is_file():
            done = "powershell CopyFromScreen (whole screen)"
    elif PLATFORM == "macos":
        run(["osascript", "-e", 'tell application "Renoise" to activate'])
        time.sleep(0.4)
        if attempt("screencapture", ["screencapture", "-x", str(out)]):
            done = "screencapture (whole screen)"
    else:
        windows = x11_renoise_windows() if os.environ.get("DISPLAY") else []
        extra = []
        if windows and which("import"):
            tried.append("import -window")
            for i, (wid, name) in enumerate(windows):
                target = out if i == 0 else out.with_name("%s-%d%s" % (out.stem, i + 1, out.suffix))
                r = run(["import", "-window", wid, str(target)], timeout=30)
                if r.returncode == 0 and target.is_file() and target.stat().st_size > 0:
                    extra.append((target, name))
            if extra and extra[0][0] == out:
                done = "import -window: %d Renoise window(s) %s" % (
                    len(extra), ", ".join('"%s"' % n for _, n in extra))
        if done:
            pass
        elif which("spectacle") and attempt("spectacle", ["spectacle", "-b", "-n", "-f", "-o", str(out)]):
            done = "spectacle (whole screen)"
        elif which("gnome-screenshot") and attempt("gnome-screenshot", ["gnome-screenshot", "-f", str(out)]):
            done = "gnome-screenshot (whole screen)"
        elif which("grim") and attempt("grim", ["grim", str(out)]):
            done = "grim (whole screen)"
    if not done:
        raise Fail("no screenshot method worked on %s (tried: %s)" % (PLATFORM, ", ".join(tried) or "nothing available"), EXIT_UNSUPPORTED)
    print("ok %s" % out)
    print("via " + done)
    for target, name in (extra[1:] if PLATFORM == "linux" and "extra" in dir() else []):
        print('%s  "%s"' % (target, name))
    return EXIT_OK


# --------------------------------------------------------------------------
# Commands: init / update-defs / doctor


ID_RE = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9_]+)*\.[A-Za-z][A-Za-z0-9_]*$")
TEXT_SUFFIXES = {".lua", ".xml", ".md", ".yml", ".yaml", ".json", ".toml", ".txt", ""}
INIT_SKIP_DIRS = {".git", "definitions", "dist", ".lls-log", "__pycache__", "renoise"}


def cmd_init(args):
    if not ID_RE.match(args.id):
        raise Fail("invalid id %r: use reverse-domain form like com.yourname.ToolName" % args.id, EXIT_USAGE)
    old_bundle = ROOT / (PLACEHOLDER_ID + ".xrnx")
    new_bundle = ROOT / (args.id + ".xrnx")
    if not old_bundle.is_dir() and not args.force:
        raise Fail("placeholder bundle %s not found; this project looks initialised already (use --force to re-run the text replacements)" % old_bundle.name)
    camel = args.id.rsplit(".", 1)[-1]
    replacements = [
        (PLACEHOLDER_ID, args.id),
        (PLACEHOLDER_NAME, args.name),
        ("MyTool", camel),
        (PLACEHOLDER_AUTHOR, args.author or PLACEHOLDER_AUTHOR),
    ]
    changed = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in INIT_SKIP_DIRS]
        for f in filenames:
            p = Path(dirpath) / f
            if p.suffix not in TEXT_SUFFIXES or p.name == "renoise.py":
                continue
            try:
                text = p.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            new = text
            for old, rep in replacements:
                new = new.replace(old, rep)
            if p.name == "README.md" and p.parent == ROOT:
                new = re.sub(r"<!-- template:start -->.*?<!-- template:end -->\n?", "", new, flags=re.S)
                new = re.sub(r"\n{3,}", "\n\n", new)
            if new != text:
                p.write_text(new)
                changed.append(p.relative_to(ROOT).as_posix())
    if old_bundle.is_dir():
        old_bundle.rename(new_bundle)
        changed.append("%s -> %s" % (old_bundle.name, new_bundle.name))
    print("ok initialised %s (%s)" % (args.id, args.name))
    for c in changed:
        print("  " + c)
    print("next: review manifest.xml, then `just check` and `just install`")
    return EXIT_OK


def github_commit(repo, ref):
    """(sha, date) of `ref` in `repo`; falls back to (ref, today) when the API is unreachable."""
    try:
        with urllib.request.urlopen("https://api.github.com/repos/%s/commits/%s" % (repo, ref), timeout=15) as r:
            info = json.load(r)
        return info["sha"], info["commit"]["committer"]["date"][:10]
    except Exception:  # noqa: BLE001 - best effort
        return ref, _dt.date.today().isoformat()


def download_repo(repo, ref, dest):
    url = "https://github.com/%s/archive/%s.tar.gz" % (repo, ref)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)
    roots = [p for p in dest.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise Fail("unexpected archive layout for %s" % url)
    return roots[0]


def replace_tree(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def cmd_update_defs(args):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        d = download_repo("renoise/definitions", args.ref, tmp / "defs")
        sha, date = github_commit("renoise/definitions", args.ref)
        defs = ROOT / "definitions"
        replace_tree(d / "library", defs / "library")
        for f in ("plugin.lua", "config.json", "LICENSE", "README.md"):
            if (d / f).exists():
                shutil.copy2(d / f, defs / f)
        patch_notes = []
        for rel, old, new, why in DEFINITION_PATCHES:
            target = defs / rel
            text = target.read_text() if target.exists() else ""
            if old in text:
                target.write_text(text.replace(old, new, 1))
                patch_notes.append("- `%s`: %s (applied)" % (rel, why))
            elif new in text:
                patch_notes.append("- `%s`: %s (already fixed upstream)" % (rel, why))
            else:
                patch_notes.append("- `%s`: %s (NOT applied: context not found, check upstream)" % (rel, why))
                print("warning: patch for %s did not apply" % rel)
        api_version = re.search(r"renoise\.API_VERSION\s*=\s*([\d.]+)", (defs / "library" / "renoise.lua").read_text())
        text = (
            "# Upstream\n\nVendored copy of the LuaCATS definitions for the Renoise Lua API.\n\n"
            "- Source: https://github.com/renoise/definitions\n- Commit: %s (%s, ref %s)\n"
            "- API version: %s\n"
            "- License: MIT (see LICENSE in this folder)\n\n"
            "Do not edit these files by hand. Refresh with `just update-defs`.\n"
            % (sha, date, args.ref, api_version.group(1) if api_version else "unknown")
        )
        if patch_notes:
            text += "\n## Local patches (re-applied by `just update-defs`)\n\n%s\n" % "\n".join(patch_notes)
        (defs / "UPSTREAM.md").write_text(text)
        print("ok definitions <- renoise/definitions@%s (%s)" % (sha[:12], date))
        for n in patch_notes:
            print("  " + n)
        x = download_repo("renoise/xrnx", args.xrnx_ref, tmp / "xrnx")
        xsha, xdate = github_commit("renoise/xrnx", args.xrnx_ref)
        docs = ROOT / "docs" / "renoise"
        replace_tree(x / "docs" / "start", docs / "start")
        replace_tree(x / "docs" / "guide", docs / "guide")
        if (x / "LICENSE").exists():
            shutil.copy2(x / "LICENSE", docs / "LICENSE")
        (docs / "UPSTREAM.md").write_text(
            "# Upstream\n\nVendored copy of the \"Renoise Scripting Development Book\" guide pages "
            "(`docs/start/*.md` and `docs/guide/*.md`).\n\n- Source: https://github.com/renoise/xrnx\n"
            "- Rendered: https://renoise.github.io/xrnx/\n- Commit: %s (%s, ref %s)\n"
            "- License: MIT (https://github.com/renoise/xrnx/blob/master/LICENSE)\n\n"
            "Links in these pages that point at `../API/...` refer to generated API pages that are not "
            "vendored; the same information lives in `definitions/library/`.\n"
            "Do not edit these files by hand. Refresh with `just update-defs`.\n" % (xsha, xdate, args.xrnx_ref)
        )
        print("ok docs/renoise <- renoise/xrnx@%s (%s)" % (xsha[:12], xdate))
    return EXIT_OK


INSTALL_HINTS = {
    "stylua": {
        "linux": "cargo install stylua --features luajit   # or download https://github.com/JohnnyMorganz/StyLua/releases",
        "wsl": "cargo install stylua --features luajit   # or download https://github.com/JohnnyMorganz/StyLua/releases",
        "macos": "brew install stylua",
        "windows": "scoop install stylua   # or winget install JohnnyMorganz.StyLua",
    },
    "lua-language-server": {
        "linux": "download https://github.com/LuaLS/lua-language-server/releases (linux-x64) and put bin/lua-language-server on PATH",
        "wsl": "download https://github.com/LuaLS/lua-language-server/releases (linux-x64) and put bin/lua-language-server on PATH",
        "macos": "brew install lua-language-server",
        "windows": "scoop install lua-language-server   # or winget install LuaLS.lua-language-server",
    },
    "just": {
        "linux": "sudo dnf install just   # or cargo install just",
        "wsl": "sudo dnf install just   # or cargo install just",
        "macos": "brew install just",
        "windows": "winget install Casey.Just   # or scoop install just",
    },
    "luajit": {
        "linux": "sudo dnf install luajit   # or sudo apt install luajit",
        "wsl": "sudo dnf install luajit   # or sudo apt install luajit",
        "macos": "brew install luajit",
        "windows": "scoop install luajit   # or download https://luajit.org/download.html",
    },
}


def tool_version(cmd):
    r = run(cmd)
    return r.stdout.strip() or r.stderr.strip() if r.returncode == 0 else None


def cmd_doctor(args):
    problems = 0
    print("platform: %s (python %s)" % (PLATFORM, sys.version.split()[0]))
    if sys.version_info < (3, 8):
        print("  !! python 3.8+ required")
        problems += 1
    for tool, cmd in (("stylua", ["stylua", "--version"]), ("lua-language-server", ["lua-language-server", "--version"]), ("just", ["just", "--version"]), ("luajit", ["luajit", "-v"])):
        v = tool_version(cmd)
        if v:
            print("%s: %s" % (tool, v))
            if tool == "lua-language-server":
                m = re.search(r"(\d+)\.(\d+)\.(\d+)", v)
                if m and tuple(int(x) for x in m.groups()) < MIN_LUALS:
                    print("  !! need lua-language-server >= %s (older versions exit 0 even when --check finds problems)" % ".".join(map(str, MIN_LUALS)))
                    problems += 1
        elif tool == "luajit" and find_lua():
            print("luajit: MISSING, `test` will use %s (LuaJIT matches Renoise better)  -> %s" % (find_lua(), INSTALL_HINTS[tool][PLATFORM]))
        else:
            print("%s: MISSING  -> %s%s" % (tool, INSTALL_HINTS[tool][PLATFORM], "   (needed by `just test`)" if tool == "luajit" else ""))
            problems += 1
    if PLATFORM == "wsl":
        print("wsl interop (powershell.exe): %s" % ("ok" if which("powershell.exe") else "MISSING (needed for screenshots, focus and locating Renoise)"))
    try:
        bundle = find_bundle(args.bundle)
        info = manifest(bundle)
        print("bundle: %s (Id %s, Version %s, ApiVersion %s)" % (bundle.name, info["Id"], info["Version"], info["ApiVersion"]))
        if info["Id"] == PLACEHOLDER_ID:
            print("  note: still the template placeholder; run `just init com.you.Name \"Name\"`")
        print("renoise prefs: %s" % renoise_version_dir())
        state, target = install_state(bundle)
        print("installed: %s (%s)" % (state, target))
        if state == "absent":
            print("  -> run `just install`")
    except Fail as e:
        print("renoise: %s" % e.reason)
        problems += 1
    try:
        reply = request(args, bundle, "ping")
        print("bridge: ok at %s:%s (boot %s, Renoise %s, API %s)" % (reply["_host"], reply["_port"], reply.get("boot_id"), reply.get("renoise_version"), reply.get("api_version")))
    except Fail as e:
        print("bridge: not reachable (%s)" % e.reason.split(".")[0])
    print("ok" if problems == 0 else "error %d problem(s)" % problems)
    return EXIT_OK if problems == 0 else EXIT_REMOTE


# --------------------------------------------------------------------------
# CLI


def build_parser():
    p = argparse.ArgumentParser(prog="renoise.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bundle", help="path to the *.xrnx folder (default: the single one in the repo root)")
    p.add_argument("--host", help="bridge host (default: 127.0.0.1, plus WSL host candidates)")
    p.add_argument("--port", type=int, help="bridge port (default: dev/.port, dev/port, or %d)" % DEFAULT_PORT)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds to wait for a reply (default %s)" % DEFAULT_TIMEOUT)
    p.add_argument("--osc-port", type=int, help="Renoise OSC server port for install/hard reload (default %d)" % DEFAULT_OSC_PORT)
    p.add_argument("--json", action="store_true", help="print one JSON object instead of text")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check tools, Renoise folders and the bridge").set_defaults(fn=cmd_doctor)
    sub.add_parser("paths", help="show detected Renoise folders and install state").set_defaults(fn=cmd_paths)

    s = sub.add_parser("install", help="install the tool into Renoise (via OSC install_tool; else link/copy)")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--link", action="store_true", help="skip OSC; symlink/junction the bundle (needs a manual reload)")
    g.add_argument("--copy", action="store_true", help="skip OSC; mirror a copy (needs a manual reload)")
    s.add_argument("--loopback", action="store_true", help="WSL: do not configure dev/bind + dev/.token (mirrored networking)")
    s.add_argument("--force", action="store_true", help="replace a tool folder this script did not create")
    s.set_defaults(fn=cmd_install)
    sub.add_parser("uninstall", help="remove the link/copy from Renoise's Tools folder").set_defaults(fn=cmd_uninstall)
    sub.add_parser("sync", help="copy mode: mirror the bundle into the installed copy").set_defaults(fn=cmd_sync)

    sub.add_parser("ping", help="is the dev bridge alive?").set_defaults(fn=cmd_ping)
    s = sub.add_parser("eval", help="run Lua inside the tool: CODE, '-' for stdin, or @file.lua")
    s.add_argument("code")
    s.set_defaults(fn=cmd_eval)
    s = sub.add_parser("reload", help="full reload via OSC install_tool (or --soft: re-require src/ in place)")
    s.add_argument("--soft", action="store_true", help="sync + APP.stop() + re-require src/ + APP.start(); keeps the Lua state")
    s.set_defaults(fn=cmd_reload)
    s = sub.add_parser("views", help="dump the view tree of registered dialogs")
    s.add_argument("--dialog", help="only this registered dialog name")
    s.add_argument("--all", action="store_true", help="include closed dialogs")
    s.set_defaults(fn=cmd_views)
    s = sub.add_parser("log", help="recent prints, errors and bridge messages")
    s.add_argument("-n", type=int, default=50)
    s.add_argument("--clear", action="store_true")
    s.set_defaults(fn=cmd_log)
    sub.add_parser("song", help="one-screen summary of the current song").set_defaults(fn=cmd_song)
    s = sub.add_parser("check", help="syntax-check main.lua and src/ with Renoise's own Lua parser")
    s.add_argument("--file", help="only this file (relative to the bundle)")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("test", help="run tests/*_test.lua under LuaJIT, no Renoise needed: [FILE ...] [-- ARGS passed to the test]")
    s.add_argument("rest", nargs=argparse.REMAINDER, help="test files (default: all tests/*_test.lua); anything after -- goes to the test")
    s.set_defaults(fn=cmd_test)
    s = sub.add_parser("screenshot", help="capture the screen/Renoise window to a PNG")
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_screenshot)
    sub.add_parser("package", help="zip the tool into dist/<Id>.xrnx (without dev/)").set_defaults(fn=cmd_package)

    s = sub.add_parser("init", help="rename the template placeholder to your tool id/name")
    s.add_argument("--id", required=True, help="e.g. com.yourname.ToolName")
    s.add_argument("--name", required=True, help='e.g. "Tool Name"')
    s.add_argument("--author", help='e.g. "Your Name [you@example.com]"')
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("update-defs", help="refresh definitions/ and docs/renoise/ from GitHub")
    s.add_argument("--ref", default="master", help="renoise/definitions ref (branch, tag or sha)")
    s.add_argument("--xrnx-ref", default="master", help="renoise/xrnx ref")
    s.set_defaults(fn=cmd_update_defs)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except Fail as e:
        if args.json:
            print(json.dumps({"status": "error", "error": e.reason, "exit": e.code}))
        else:
            print("error " + e.reason)
            if e.payload:
                print(e.payload)
        return e.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
