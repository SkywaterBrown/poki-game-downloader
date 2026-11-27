#!/usr/bin/env python3
"""
poki_cdp.py — Download a Poki game by driving your installed Chrome via CDP.

Requirements:
    pip install websocket-client

Usage:
    python poki_cdp.py https://poki.com/en/g/dan-the-man D:\\DanTheMan --wait 300
    python poki_cdp.py <url> <dest> --wait 60 --verbose
"""

import argparse
import base64
import http.server
import json
import os
import select
import socketserver
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from urllib.parse import unquote, urlparse

try:
    import websocket
except ImportError:
    sys.exit("ERROR: pip install websocket-client")


CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Chrome/Edge not found. Edit CHROME_CANDIDATES.")


def launch_chrome(port=9222, headless=False, profile_dir=None):
    """Launch Chrome at about:blank — caller navigates AFTER enabling Network."""
    exe = find_chrome()
    profile_dir = profile_dir or os.path.join(tempfile.gettempdir(), "poki-cdp-profile")
    os.makedirs(profile_dir, exist_ok=True)
    args = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=IsolateOrigins,site-per-process",
    ]
    if headless:
        args.append("--headless=new")
    args.append("about:blank")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, port


def wait_for_cdp(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                json.loads(r.read())
                return True
        except Exception:
            time.sleep(0.3)
    return False


# ---------------------------------------------------------------------------
# CDP client — buffers events seen during command responses
# ---------------------------------------------------------------------------

class CDPClient:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0
        self._events = []

    def send(self, method, params=None):
        """Send command, wait for its response, BUFFER any events in the meantime."""
        self._id += 1
        msg_id = self._id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            data = json.loads(self.ws.recv())
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(data["error"])
                return data.get("result", {})
            if "method" in data:
                self._events.append(data)  # don't discard

    def read_event(self, timeout=1.0):
        """Return next event (buffered first, else fresh), or None on timeout."""
        if self._events:
            return self._events.pop(0)
        try:
            if not self.ws.sock:
                return None
            r, _, _ = select.select([self.ws.sock], [], [], timeout)
            if not r:
                return None
            data = json.loads(self.ws.recv())
            if "method" in data:
                return data
        except Exception:
            return None
        return None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Save-path mapping
# ---------------------------------------------------------------------------

_known_game_hosts = set()


def _note_host(url):
    parsed = urlparse(url)
    if parsed.path.endswith("/index.html"):
        _known_game_hosts.add(parsed.netloc.lower())


def save_path_for(url, dest):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = unquote(parsed.path)

    # Primary game CDN pattern
    if host.endswith(".gdn.poki.com"):
        parts = path.lstrip("/").split("/", 1)
        if len(parts) == 2 and parts[1]:
            return os.path.join(dest, parts[1])

    # Poki SDK scripts referenced from index.html's own directory
    if host == "game-cdn.poki.com" and "poki-sdk" in path.lower() and path.endswith(".js"):
        return os.path.join(dest, os.path.basename(path))

    # Fallback: any host that served the game's index.html
    if host in _known_game_hosts:
        parts = path.lstrip("/").split("/", 1)
        if len(parts) == 2 and parts[1]:
            return os.path.join(dest, parts[1])
        return os.path.join(dest, path.lstrip("/"))

    return None


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def capture(url, dest, wait_seconds=120, headless=False, verbose=False):
    os.makedirs(dest, exist_ok=True)
    proc, port = launch_chrome(headless=headless)
    print(f"[*] Chrome launched (pid {proc.pid}, CDP port {port})")

    if not wait_for_cdp(port):
        proc.terminate()
        sys.exit("ERROR: Chrome did not open the CDP port.")

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as r:
        targets = json.loads(r.read())
    page_target = next((t for t in targets if t.get("type") == "page"), None)
    if not page_target:
        proc.terminate()
        sys.exit("ERROR: no page target.")

    client = CDPClient(page_target["webSocketDebuggerUrl"])

    # Enable Network BEFORE navigating — critical.
    client.send("Network.enable", {
        "maxTotalBufferSize": 200_000_000,
        "maxResourceBufferSize": 100_000_000,
    })
    client.send("Page.enable")
    print("[*] Network capture enabled. Navigating to game...")
    client.send("Page.navigate", {"url": url})
    print("[*] Page loading. Play the game now — every request is being recorded.")

    saved = 0
    pending = {}          # requestId -> {"url", "response"}
    missed = []           # [(url, reason)]
    event_counts = {}     # method -> count
    hosts_seen = set()

    def handle_event(msg):
        nonlocal saved
        method = msg.get("method")
        if verbose:
            print(f"    [event] {method}")
        if method:
            event_counts[method] = event_counts.get(method, 0) + 1

        if method == "Network.responseReceived":
            params = msg.get("params", {})
            rid = params.get("requestId")
            resp = params.get("response", {})
            req_url = resp.get("url", "")
            if req_url:
                _note_host(req_url)
                try:
                    hosts_seen.add(urlparse(req_url).netloc.lower())
                except Exception:
                    pass
            pending[rid] = {"url": req_url, "response": resp}

        elif method == "Network.loadingFinished":
            params = msg.get("params", {})
            rid = params.get("requestId")
            info = pending.pop(rid, None)
            if not info:
                return
            req_url = info["url"]
            sp = save_path_for(req_url, dest)
            if not sp:
                return

            try:
                body_res = client.send("Network.getResponseBody", {"requestId": rid})
                body = body_res.get("body", "")
                data = base64.b64decode(body) if body_res.get("base64Encoded") else body.encode("utf-8")

                os.makedirs(os.path.dirname(sp) or dest, exist_ok=True)
                with open(sp, "wb") as f:
                    f.write(data)
                saved += 1
                print(f"  [{saved:3d}] {os.path.relpath(sp, dest)[:70]} ({len(data)} B)")
            except Exception as e:
                missed.append((req_url, str(e)))
                print(f"  [!] failed to save {os.path.basename(sp)}: {e}")

    # Main capture loop
    end = time.time() + wait_seconds
    while time.time() < end:
        msg = client.read_event(timeout=1.0)
        if msg:
            try:
                handle_event(msg)
            except Exception as e:
                print(f"[!] handler error: {e}")

    # Drain buffered events
    print("[*] Draining remaining network events...")
    drain_end = time.time() + 2
    while time.time() < drain_end:
        msg = client.read_event(timeout=0.3)
        if not msg:
            break
        try:
            handle_event(msg)
        except Exception:
            pass

    client.close()
    try:
        proc.terminate()
    except Exception:
        pass

    print(f"\n[*] Saved {saved} file(s) to {dest}")
    print(f"[*] Known game hosts: {sorted(_known_game_hosts)}")
    print(f"[*] All hosts seen ({len(hosts_seen)}): {sorted(hosts_seen)}")
    interesting = {k: v for k, v in event_counts.items()
                   if k in ("Network.responseReceived", "Network.loadingFinished", "Network.loadingFailed")}
    print(f"[*] Event counts: {interesting}")
    if pending:
        print(f"[!] {len(pending)} request(s) still in-flight when capture stopped")
    if missed:
        print(f"[!] {len(missed)} file(s) failed:")
        for u, why in missed[:10]:
            print(f"    {os.path.basename(u):50s} — {why}")
        if len(missed) > 10:
            print(f"    ... and {len(missed)-10} more")

    return os.path.exists(os.path.join(dest, "index.html"))


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

MIME = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".js":   "application/javascript",   ".mjs": "application/javascript",
    ".json": "application/json",         ".wasm": "application/wasm",
    ".css":  "text/css",
    ".png":  "image/png",   ".jpg": "image/jpeg",  ".jpeg": "image/jpeg",
    ".gif":  "image/gif",   ".svg": "image/svg+xml", ".webp": "image/webp",
    ".ico":  "image/x-icon",
    ".webm": "video/webm",  ".mp4": "video/mp4",
    ".ogg":  "audio/ogg",   ".mp3": "audio/mpeg",  ".wav": "audio/wav",
    ".woff": "font/woff",   ".woff2": "font/woff2", ".otf": "font/otf",
    ".ttf":  "font/ttf",    ".xml": "application/xml",
    ".txt":  "text/plain; charset=utf-8",
    ".projectc": "application/octet-stream",
    ".arci":     "application/octet-stream",
    ".arcd":     "application/octet-stream",
}


class GameHandler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        return MIME.get(ext, "application/octet-stream")

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "unsafe-none")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


class ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(directory, port=8000, open_browser=True):
    directory = os.path.abspath(directory)
    handler = lambda *a, **kw: GameHandler(*a, directory=directory, **kw)
    httpd = ThreadedServer(("", port), handler)
    url = f"http://localhost:{port}/index.html"
    print(f"\n{'='*60}\n  READY TO PLAY\n{'='*60}")
    print(f"  Folder : {directory}\n  URL    : {url}\n  Stop   : Ctrl+C\n{'='*60}\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    with httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Server stopped.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Download and serve a Poki game via CDP.")
    ap.add_argument("url")
    ap.add_argument("dest")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--wait", type=int, default=120)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="Log every CDP event")
    ap.add_argument("--no-serve", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    ok = capture(args.url, args.dest, wait_seconds=args.wait,
                 headless=args.headless, verbose=args.verbose)
    if not ok:
        sys.exit(1)
    if not args.no_serve:
        serve(args.dest, port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()