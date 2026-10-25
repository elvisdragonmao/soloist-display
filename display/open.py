#!/usr/bin/env python3
"""Open the now-playing display full screen in a Chromium-family browser, or
bring it back to the front if it is already open. Runs at login, and on the Pi
from Ctrl+Alt+P and the menu entry. Linux, macOS and Windows.

    open.py [--url URL] [--browser PATH] [--print]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

URL = os.environ.get("SOLOIST_DISPLAY_URL", "http://127.0.0.1:8787/")
# Chromium names an --app window after its host; --class is ignored on Wayland.
APP_ID = "chrome-127.0.0.1__-Default"


def profile_dir():
    """A browser profile of its own, so the display never mixes with someone's browsing."""
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    elif os.name == "nt":
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "soloist-display" / "browser"


def find_browser():
    if os.environ.get("SOLOIST_DISPLAY_BROWSER"):
        return os.environ["SOLOIST_DISPLAY_BROWSER"]
    if sys.platform == "darwin":
        apps = ["Google Chrome", "Chromium", "Microsoft Edge", "Brave Browser"]
        for root in ("/Applications", Path.home() / "Applications"):
            for app in apps:
                exe = Path(root) / f"{app}.app/Contents/MacOS/{app}"
                if exe.exists():
                    return str(exe)
        return None
    if os.name == "nt":
        roots = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        exes = [r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe",
                r"BraveSoftware\Brave-Browser\Application\brave.exe"]
        for exe in exes:
            for root in filter(None, roots):
                if (Path(root) / exe).exists():
                    return str(Path(root) / exe)
        return None
    names = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
             "microsoft-edge", "microsoft-edge-stable", "brave-browser"]
    return next(filter(None, map(shutil.which, names)), None)


def get_json(path, timeout=2):
    with urllib.request.urlopen(URL.rstrip("/") + path, timeout=timeout) as res:
        return json.load(res)


def wait_for_server(seconds=60):
    """At login the server may still be starting."""
    for _ in range(seconds):
        try:
            return get_json("/api/status")
        except OSError:
            time.sleep(1)
    return None


def focus_existing():
    """Bring an open display to the front, full screen. True if it was open."""
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") and shutil.which("wlrctl"):
        match = f"app_id:{APP_ID}"
        if subprocess.run(["wlrctl", "toplevel", "find", match]).returncode != 0:
            return False
        subprocess.run(["wlrctl", "toplevel", "focus", match])
        if subprocess.run(["wlrctl", "toplevel", "find", match, "state:fullscreen"]).returncode != 0:
            subprocess.run(["wlrctl", "toplevel", "fullscreen", match])
        return True
    return False


def main():
    global URL
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=URL)
    parser.add_argument("--browser", help="browser executable (default: Chrome, Chromium, Edge or Brave)")
    parser.add_argument("--print", action="store_true", help="print the browser command instead of running it")
    args = parser.parse_args()
    URL = args.url

    if focus_existing():
        return
    status = wait_for_server()
    if status is None:
        sys.exit(f"the display server is not answering at {URL}")
    if status.get("display_open") and not args.print:
        print("the display is already open")
        return

    browser = args.browser or find_browser()
    if not browser:
        sys.exit("no Chromium-family browser found; install Chrome, Chromium or Edge, or pass --browser")
    cmd = [
        browser,
        f"--user-data-dir={profile_dir()}",
        f"--app={URL}",
        "--start-fullscreen",
        "--no-first-run",
        "--no-default-browser-check",
        "--noerrdialogs",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--disable-features=Translate,TranslateUI",
        "--check-for-update-interval=31536000",
    ]
    if sys.platform.startswith("linux"):
        # No keyring prompt on a kiosk with nobody to type a password.
        cmd.append("--password-store=basic")
        if os.environ.get("WAYLAND_DISPLAY"):
            cmd.append("--ozone-platform=wayland")
    if args.print:
        print(subprocess.list2cmdline(cmd) if os.name == "nt" else " ".join(map(str, cmd)))
        return

    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
