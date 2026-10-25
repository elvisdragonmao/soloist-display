#!/usr/bin/env python3
"""Download the latest Soloist build and install it if it differs from the
installed one. Spotify's Soloist builds expire 90 days after release (the
binary then exits with code 10) and do not recover by restarting, so this runs
daily. Linux, macOS and Windows; standard library only.

    update.py                       install if new and nothing is playing
    update.py --force               install even while music is playing
    update.py --restart systemd:spotify-soloist --user sdc    (the Pi, as root)
    update.py --restart pid         stop the running Soloist; run.py restarts it
"""

import argparse
import filecmp
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

CDN = "https://soloist-builds.spotifycdn.com/"
EXE = "soloist.exe" if os.name == "nt" else "soloist"


def build_name():
    """The release archive for this machine, as listed in Spotify's Soloist docs."""
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        if machine != "arm64":
            sys.exit("Soloist for macOS is Apple Silicon (arm64) only")
        return "soloist_release_osx_arm64.tar.gz"
    if os.name == "nt":
        return "soloist_release_windows_x86_64.zip"
    if machine in ("aarch64", "arm64"):
        return "soloist_release_arm64.tar.gz"
    if machine.startswith("arm"):
        return "soloist_release_arm32.tar.gz"
    if machine in ("x86_64", "amd64"):
        return "soloist_release_x86_64.tar.gz"
    sys.exit(f"no Soloist build for {machine}")


def default_bin():
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/soloist-display/bin" / EXE
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "soloist-display" / "bin" / EXE
    if os.geteuid() == 0:
        return Path("/usr/local/bin") / EXE
    return Path.home() / ".local/bin" / EXE


def soloist_data_dir():
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/soloist"
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "soloist" / "data"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "soloist"


def download(url, work):
    archive = work / url.rsplit("/", 1)[-1]
    with urllib.request.urlopen(url, timeout=120) as res, open(archive, "wb") as out:
        shutil.copyfileobj(res, out)
    unpacked = work / "x"
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(unpacked)
    else:
        with tarfile.open(archive) as t:
            if hasattr(tarfile, "data_filter"):
                t.extractall(unpacked, filter="data")
            else:
                t.extractall(unpacked)
    found = next(unpacked.rglob(EXE), None)
    if not found:
        sys.exit(f"{EXE} not found in {url}")
    found.chmod(0o755)
    return found


def version(exe):
    try:
        return subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except OSError:
        return "none"


def as_user(user, cmd):
    """Run cmd as `user` when we are root (the Pi's updater), else as ourselves."""
    if user and os.name != "nt" and os.geteuid() == 0:
        return ["runuser", "-u", user, "--", *cmd]
    return cmd


def is_playing(exe, user):
    try:
        out = subprocess.run(as_user(user, [str(exe), "ctl", "now", "--json"]),
                             capture_output=True, text=True, timeout=15).stdout
        return json.loads(out).get("status") == "playing"
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def restart(mode, user):
    if mode == "none":
        return
    if mode.startswith("systemd:"):
        unit = mode.split(":", 1)[1]
        cmd = ["systemctl", "--user"]
        if user and os.geteuid() == 0:
            cmd.append(f"--machine={user}@.host")
        subprocess.run([*cmd, "restart", unit], check=True)
    elif mode == "pid":
        # run.py notices Soloist exited and starts the new binary.
        try:
            pid = int((soloist_data_dir() / "soloist.pid").read_text().strip())
        except (OSError, ValueError):
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    else:
        sys.exit(f"unknown --restart mode: {mode}")


def main():
    parser = argparse.ArgumentParser(description="Install the latest Soloist build.")
    parser.add_argument("--bin", type=Path, default=default_bin(), help="installed binary (default: %(default)s)")
    parser.add_argument("--url", help="release archive (default: the build for this machine)")
    parser.add_argument("--restart", default="none", help="systemd:<unit>, pid or none (default)")
    parser.add_argument("--user", help="the user Soloist runs as, when running as root")
    parser.add_argument("--force", action="store_true", help="install even while music is playing")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        new = download(args.url or CDN + build_name(), Path(tmp))
        installed = args.bin.exists()
        if installed and filecmp.cmp(new, args.bin, shallow=False):
            print(f"up to date: {version(args.bin)}")
            return
        print(f"installed: {version(args.bin) if installed else 'none'}")
        print(f"available: {version(new)}")

        if installed and not args.force and is_playing(args.bin, args.user):
            print("music is playing, deferring the update (run with --force to install now)")
            return

        # Swap by renaming, which works even while the old binary runs (on
        # Windows too), and keep the old one as .prev.
        args.bin.parent.mkdir(parents=True, exist_ok=True)
        staged = args.bin.with_name(args.bin.name + ".new")
        shutil.copy2(new, staged)
        staged.chmod(0o755)
        if installed:
            prev = args.bin.with_name(args.bin.name + ".prev")
            prev.unlink(missing_ok=True)
            os.replace(args.bin, prev)
        os.replace(staged, args.bin)

    if installed:
        restart(args.restart, args.user)
    print(f"updated to: {version(args.bin)}")


if __name__ == "__main__":
    main()
