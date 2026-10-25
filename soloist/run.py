#!/usr/bin/env python3
"""Keep Soloist running on macOS and Windows (Linux uses spotify-soloist.service).

Reads the device name and API key from the config file, restarts Soloist when it
exits, and installs a new build at once when the current one has expired
(exit code 10).

    run.py [--bin PATH] [--config PATH]
"""

import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from update import default_bin  # noqa: E402

EXPIRED = 10


def default_config():
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/soloist-display/soloist.env"
    if os.name == "nt":
        return Path(os.environ["APPDATA"]) / "soloist-display" / "soloist.env"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "soloist" / "soloist.env"


def read_env(path):
    env = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", type=Path, default=default_bin())
    parser.add_argument("--config", type=Path, default=default_config())
    args = parser.parse_args()

    env = read_env(args.config)
    if not env.get("SOLOIST_API_KEY") or env["SOLOIST_API_KEY"].startswith("spak_REPLACE"):
        sys.exit(f"set SOLOIST_API_KEY in {args.config}")
    cmd = [
        str(args.bin),
        "--device-name", env.get("SOLOIST_DEVICE_NAME") or "Soloist",
        "--api-key", env["SOLOIST_API_KEY"],
        "--ws", "127.0.0.1:0",
        *shlex.split(env.get("SOLOIST_EXTRA_ARGS", "")),
    ]
    update = [sys.executable, str(HERE / "update.py"), "--bin", str(args.bin), "--force"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    child = None

    def stop(*_):
        if child and child.poll() is None:
            child.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)

    while True:
        if not args.bin.exists():
            subprocess.run(update, creationflags=flags)
        started = time.monotonic()
        child = subprocess.Popen(cmd, creationflags=flags)
        code = child.wait()
        if code == EXPIRED:
            print("Soloist build expired, updating", flush=True)
            subprocess.run(update, creationflags=flags)
            continue
        # Restarted at once after an update stopped it; otherwise don't spin.
        time.sleep(1 if time.monotonic() - started > 60 else 5)


if __name__ == "__main__":
    main()
