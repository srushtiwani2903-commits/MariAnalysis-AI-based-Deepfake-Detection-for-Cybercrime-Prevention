"""Watches backend sources + .env and restarts run.py on any change.

On Windows this replaces Flask's own reloader so a single clean process runs
and the SQLite DB never gets locked by an orphan reloader parent.

Usage: python dev_restart.py  (keep running)
"""
import os
import socket
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(BASE, ".venv", "Scripts", "python.exe")
LOG_FILE = os.path.join(BASE, "dev_restart.log")
SKIP_DIRS = {"instance", "uploads", "reports", "security", ".venv", "__pycache__", "node_modules"}
WATCH_EXTS = {".py", ".json"}


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def snapshot():
    files = {}
    for root, dirs, names in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for n in names:
            if n == ".env" or os.path.splitext(n)[1] in WATCH_EXTS:
                p = os.path.join(root, n)
                try:
                    files[p] = os.path.getmtime(p)
                except OSError:
                    pass
    return files


def port_free(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.5)
    return False


def start_server():
    proc = subprocess.Popen(
        [PYTHON, os.path.join(BASE, "run.py")],
        cwd=BASE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    if port_free(5000):
        log(f"backend up (pid {proc.pid})")
    else:
        log(f"backend pid {proc.pid} started but port 5000 did not open")
    return proc


def stop_server(proc):
    if proc and proc.poll() is None:
        # taskkill /T kills the whole tree: the venv python.exe is a shim that
        # spawns the real python, so proc.kill() alone would leak the child.
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            log("could not stop backend cleanly")
    port_free(5000)


def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")
    log("watching backend sources (.py, .env, .json)")
    last = snapshot()
    proc = start_server()
    while True:
        time.sleep(1.0)
        snap = snapshot()
        if snap == last:
            continue
        changed = sorted(p for p in snap if last.get(p) != snap.get(p))
        last = snap
        log(f"change: {', '.join(os.path.relpath(p, BASE) for p in changed[:5])} -> restarting")
        stop_server(proc)
        proc = start_server()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("watcher stopped")
