#!/usr/bin/env python3
"""Local server for the Soloist now-playing display.

Serves the web UI, tells it where Soloist's WebSocket API listens (Soloist
picks a random port and writes it to its data dir), and looks up synced lyrics
on LRCLIB with an on-disk cache. Standard library only; runs on Linux, macOS
and Windows.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent / "web"
HOME = Path.home()


def soloist_data_dir():
    """Where Soloist writes ws.addr and ws.port: its default data dir per platform."""
    if os.environ.get("SOLOIST_DATA_DIR"):
        return Path(os.environ["SOLOIST_DATA_DIR"])
    if sys.platform == "darwin":
        return HOME / "Library/Application Support/soloist"
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "soloist" / "data"
    return Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "soloist"


def cache_dir():
    if sys.platform == "darwin":
        return HOME / "Library/Caches/soloist-display"
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "soloist-display" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "soloist-display"


SOLOIST_DATA = soloist_data_dir()
CACHE_DIR = cache_dir() / "lyrics"

LRCLIB = "https://lrclib.net/api"
USER_AGENT = "soloist-display (https://github.com/elvisdragonmao/soloist-display)"
# A track LRCLIB had nothing for is asked again after this long.
MISS_TTL = 6 * 3600
# The display window as wlroots compositors know it (see open.py).
APP_ID = os.environ.get("SOLOIST_DISPLAY_APP_ID", "chrome-127.0.0.1__-Default")


def lrclib(path, params):
    url = f"{LRCLIB}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def pick(record):
    return {
        "synced": record.get("syncedLyrics"),
        "plain": record.get("plainLyrics"),
        "instrumental": bool(record.get("instrumental")),
        "source": f"lrclib:{record.get('id')}",
    }


def find_lyrics(track, artist, album, duration):
    """Exact match first, then the closest search result that has synced lyrics."""
    params = {"track_name": track, "artist_name": artist}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = round(duration)
    record = lrclib("get", params)
    if record and (record.get("syncedLyrics") or record.get("instrumental")):
        return pick(record)

    results = lrclib("search", {"track_name": track, "artist_name": artist}) or []

    def score(r):
        off = abs((r.get("duration") or 0) - duration) if duration else 0
        return (not r.get("syncedLyrics"), off)

    results = [r for r in results if not duration or abs((r.get("duration") or 0) - duration) <= 4]
    results.sort(key=score)
    if results:
        return pick(results[0])
    if record:
        return pick(record)
    return None


def cached_lyrics(key, track, artist, album, duration):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        data = json.loads(path.read_text())
        if data.get("found") or time.time() - data.get("at", 0) < MISS_TTL:
            return data
    lyrics = find_lyrics(track, artist, album, duration)
    data = {"found": lyrics is not None, "at": time.time(), **(lyrics or {})}
    path.write_text(json.dumps(data, ensure_ascii=False))
    return data


def press_fullscreen_key():
    """Press the browser's full-screen key in the display window. A page cannot
    leave the browser's own full screen (--start-fullscreen) by script, so the
    server does it. The window was just clicked, so it has the focus."""
    if sys.platform == "darwin":
        # Needs Accessibility permission for the Python that runs this server.
        script = 'tell application "System Events" to keystroke "f" using {control down, command down}'
        cmds = [["osascript", "-e", script]]
    elif os.name == "nt":
        cmds = [["powershell", "-NoProfile", "-Command", "(New-Object -ComObject WScript.Shell).SendKeys('{F11}')"]]
    elif os.environ.get("WAYLAND_DISPLAY") and shutil.which("wtype"):
        cmds = [["wtype", "-k", "F11"]]
        if shutil.which("wlrctl"):
            cmds.insert(0, ["wlrctl", "toplevel", "focus", f"app_id:{APP_ID}"])
    elif os.environ.get("DISPLAY") and shutil.which("xdotool"):
        cmds = [["xdotool", "key", "F11"]]
    else:
        raise FileNotFoundError("no tool to press F11 (install wtype on Wayland or xdotool on X11)")
    for cmd in cmds:
        subprocess.run(cmd, timeout=5, check=True)


def soloist_ws_url():
    try:
        addr = (SOLOIST_DATA / "ws.addr").read_text().strip()
        port = (SOLOIST_DATA / "ws.port").read_text().strip()
    except OSError:
        return None
    return f"ws://{addr}:{port}"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/api/config":
            return self.send_json({"ws": soloist_ws_url()})
        if url.path == "/api/status":
            # The page pings every 15 s, slower when hidden (Chrome throttles timers).
            seen = self.server.last_ping
            return self.send_json({"display_open": seen is not None and time.time() - seen < 90})
        if url.path == "/api/lyrics":
            return self.lyrics(urllib.parse.parse_qs(url.query))
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        # Only the display page itself, not some other site open in a browser.
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            return self.send_json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        if path == "/api/ping":
            self.server.last_ping = time.time()
            return self.send_json({"ok": True})
        if path != "/api/fullscreen":
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            press_fullscreen_key()
        except FileNotFoundError as e:
            return self.send_json({"error": str(e)}, HTTPStatus.NOT_IMPLEMENTED)
        except (OSError, subprocess.SubprocessError) as e:
            return self.send_json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return self.send_json({"ok": True})

    def lyrics(self, query):
        q = {k: v[0] for k, v in query.items()}
        track_id = q.get("id", "").rsplit(":", 1)[-1]
        if not track_id.isalnum() or not q.get("track") or not q.get("artist"):
            return self.send_json({"error": "id, track and artist are required"}, HTTPStatus.BAD_REQUEST)
        try:
            duration = float(q.get("duration") or 0)
            data = cached_lyrics(track_id, q["track"], q["artist"], q.get("album"), duration)
        except (OSError, ValueError, urllib.error.URLError) as e:
            return self.send_json({"error": str(e)}, HTTPStatus.BAD_GATEWAY)
        return self.send_json(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.last_ping = None
    print(f"serving on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
