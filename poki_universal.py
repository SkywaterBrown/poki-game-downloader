#!/usr/bin/env python3
"""
poki_universal.py — Manifest-first Poki game downloader.

Supported engines:
  • Defold        (Dan the Man)     — byte-verified against archive_files.json
  • Construct 3   (Stick Fighter)   — file-count verified against data.json + index.html
  • Unity / Godot / GameMaker / PlayCanvas / Fancade / Clickteam
                                    — traffic-capture fallback (with --auto-boot)

New in this version:
  --auto-boot       Stop capture when the network goes idle (faster, adaptive)
  --quiet-seconds N Seconds of network silence before auto-boot stops (default 5)
  --min-boot N      Minimum seconds to capture even if network is idle (default 10)

Usage:
    python poki_universal.py <url> <dest> --port 8004
    python poki_universal.py <url> <dest> --port 8004 --auto-boot --max-boot 180
"""

import argparse
import base64
import concurrent.futures
import http.server
import json
import os
import re
import select
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from urllib.parse import quote as url_quote
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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")


def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Chrome/Edge not found.")


# ---------------------------------------------------------------------------
# Chrome + CDP
# ---------------------------------------------------------------------------

def launch_chrome(port=9222, headless=False):
    profile_dir = os.path.join(tempfile.gettempdir(), "poki-universal-profile")

    # Zombie-Chrome guard
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"],
                       capture_output=True, timeout=5)
    except Exception:
        pass
    try:
        import shutil
        if os.path.exists(profile_dir):
            shutil.rmtree(profile_dir, ignore_errors=True)
    except Exception:
        pass
    os.makedirs(profile_dir, exist_ok=True)

    args = [
        find_chrome(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run", "--no-default-browser-check",
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


class CDPClient:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0
        self._events = []

    def send(self, method, params=None):
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
                self._events.append(data)

    def read_event(self, timeout=1.0):
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
# URL → disk path mapping
# ---------------------------------------------------------------------------

_known_hosts = set()


def _note_host(url):
    if urlparse(url).path.endswith("/index.html"):
        _known_hosts.add(urlparse(url).netloc.lower())


def save_path_for(url, dest):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = unquote(parsed.path)

    if host.endswith(".gdn.poki.com"):
        parts = path.lstrip("/").split("/", 1)
        if len(parts) == 2 and parts[1]:
            return os.path.join(dest, parts[1])

    if host == "game-cdn.poki.com" and "poki-sdk" in path.lower() and path.endswith(".js"):
        return os.path.join(dest, os.path.basename(path))

    if host in _known_hosts:
        parts = path.lstrip("/").split("/", 1)
        if len(parts) == 2 and parts[1]:
            return os.path.join(dest, parts[1])
        return os.path.join(dest, path.lstrip("/"))

    return None


def safe_quote(s):
    if "%" in s:
        return s
    return url_quote(s, safe="/")


# ---------------------------------------------------------------------------
# Engine detection
# ---------------------------------------------------------------------------

def detect_engine(url):
    path = urlparse(url).path
    if path.endswith("/archive_files.json"):
        return ("defold", url)
    if path.endswith("/data.json"):
        return ("construct3", url)
    return (None, None)


# ---------------------------------------------------------------------------
# Manifest reading + enumerators
# ---------------------------------------------------------------------------

def read_manifest(url, dest):
    sp = save_path_for(url, dest)
    if sp and os.path.exists(sp):
        with open(sp, "rb") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def read_index_html(base_url, dest):
    index_url = base_url.rstrip("/") + "/index.html"
    sp = save_path_for(index_url, dest)
    if sp and os.path.exists(sp):
        with open(sp, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    req = urllib.request.Request(index_url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def enumerate_defold(manifest_url, dest):
    raw = read_manifest(manifest_url, dest)
    data = json.loads(raw)
    manifest_dir = manifest_url.rsplit("/", 1)[0]
    expected = {}
    for entry in data.get("content", []):
        pieces = entry.get("pieces", [])
        entry_size = entry.get("size", 0)
        if len(pieces) == 1:
            expected[f"{manifest_dir}/{pieces[0]['name']}"] = entry_size
        else:
            for piece in pieces:
                expected[f"{manifest_dir}/{piece['name']}"] = None
    return expected, data


def enumerate_construct3(manifest_url, dest):
    raw = read_manifest(manifest_url, dest)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[!] data.json is not valid JSON: {e}")
        return None, None

    base_url = manifest_url.rsplit("/", 1)[0]
    expected = {}

    try:
        index_html = read_index_html(base_url, dest)
        for pattern in [r'<script[^>]+src=["\']([^"\']+)["\']',
                        r'<link[^>]+href=["\']([^"\']+)["\']']:
            for m in re.finditer(pattern, index_html):
                ref = m.group(1)
                if ref.startswith(("http://", "https://", "//", "data:")):
                    continue
                ref = ref.lstrip("./").lstrip("/")
                if ref:
                    expected[f"{base_url}/{ref}"] = None
    except Exception as e:
        print(f"[!] index.html parse failed: {e}")

    images = data.get("images", {})
    image_items = []
    if isinstance(images, dict):
        image_items = list(images.items())
    elif isinstance(images, list):
        image_items = [(i.get("name", f"img{k}"), i) for k, i in enumerate(images) if isinstance(i, dict)]

    for img_name, img_info in image_items:
        if not isinstance(img_info, dict):
            continue
        for k, sheet in enumerate(img_info.get("sheets", [])):
            if isinstance(sheet, dict) and "file" in sheet:
                fname = sheet["file"]
            else:
                fname = f"{img_name}-sheet{k}.png"
            expected[f"{base_url}/images/{safe_quote(fname)}"] = None

    for key in ("sounds", "music"):
        items = data.get(key, {})
        item_list = []
        if isinstance(items, dict):
            item_list = list(items.items())
        elif isinstance(items, list):
            item_list = [(i.get("name", f"snd{k}"), i) for k, i in enumerate(items) if isinstance(i, dict)]
        for snd_name, snd_info in item_list:
            if not isinstance(snd_info, dict):
                continue
            fname = snd_info.get("file", f"{snd_name}.webm")
            expected[f"{base_url}/media/{safe_quote(fname)}"] = None

    fonts = data.get("fonts", {})
    font_items = []
    if isinstance(fonts, dict):
        font_items = list(fonts.items())
    elif isinstance(fonts, list):
        font_items = [(i.get("name", f"font{k}"), i) for k, i in enumerate(fonts) if isinstance(i, dict)]
    for font_name, font_info in font_items:
        if not isinstance(font_info, dict):
            continue
        fname = font_info.get("file", f"{font_name}.otf")
        expected[f"{base_url}/fonts/{safe_quote(fname)}"] = None

    text = raw.decode("utf-8", errors="replace")
    for pattern, folder in [
        (r'"([^"\\]+?\.png)"', "images"),
        (r'"([^"\\]+?\.webm)"', "media"),
        (r'"([^"\\]+?\.m4a)"', "media"),
        (r'"([^"\\]+?\.mp3)"', "media"),
        (r'"([^"\\]+?\.ogg)"', "media"),
        (r'"([^"\\]+?\.otf)"', "fonts"),
        (r'"([^"\\]+?\.ttf)"', "fonts"),
        (r'"([^"\\]+?\.woff2?)"', "fonts"),
    ]:
        for m in re.finditer(pattern, text):
            fname = m.group(1)
            rel = fname if "/" in fname else f"{folder}/{fname}"
            expected[f"{base_url}/{safe_quote(rel)}"] = None

    return expected, data


# ---------------------------------------------------------------------------
# Missing-file detection + download
# ---------------------------------------------------------------------------

def find_work(expected, dest):
    work = []
    for url, size in expected.items():
        sp = save_path_for(url, dest)
        if not sp:
            continue
        if not os.path.exists(sp):
            work.append((url, size, "missing"))
            continue
        if size is not None:
            actual = os.path.getsize(sp)
            if actual != size:
                work.append((url, size, f"partial ({actual}B)"))
    return work


def download_one(item, dest, counter, lock):
    url, expected_size, _reason = item
    sp = save_path_for(url, dest)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if expected_size is not None and len(data) != expected_size:
            return (url, False, f"size {len(data)} != {expected_size}")
        os.makedirs(os.path.dirname(sp) or dest, exist_ok=True)
        with open(sp, "wb") as f:
            f.write(data)
        with lock:
            counter[0] += 1
            n = counter[0]
        print(f"  [{n}/{counter[1]}] {os.path.relpath(sp, dest):55s} ({len(data):>10} B)")
        return (url, True, None)
    except Exception as e:
        return (url, False, str(e))


def download_missing(work, dest):
    if not work:
        return
    print(f"\n[*] Downloading {len(work)} file(s)...")
    counter = [0, len(work)]
    lock = threading.Lock()
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futures = [ex.submit(download_one, item, dest, counter, lock) for item in work]
        for f in concurrent.futures.as_completed(futures):
            url, ok, why = f.result()
            if not ok:
                failures.append((url, why))
    if failures:
        print(f"\n[!] {len(failures)} file(s) failed")
        for u, w in failures[:5]:
            print(f"    {os.path.basename(u):40s} — {w}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_defold(manifest_data, manifest_url, dest):
    manifest_dir = manifest_url.rsplit("/", 1)[0]
    all_ok = True
    total_expected = 0
    total_actual = 0
    for entry in manifest_data.get("content", []):
        pieces = entry.get("pieces", [])
        entry_size = entry.get("size", 0)
        entry_actual = 0
        missing = []
        for piece in pieces:
            url = f"{manifest_dir}/{piece['name']}"
            sp = save_path_for(url, dest)
            if sp and os.path.exists(sp):
                entry_actual += os.path.getsize(sp)
            else:
                missing.append(piece["name"])
        mark = "✅" if (entry_actual == entry_size and not missing) else "❌"
        if mark == "❌":
            all_ok = False
        total_expected += entry_size
        total_actual += entry_actual
        piece_info = f"({len(pieces)}/{len(pieces)} pieces)" if len(pieces) > 1 else ""
        print(f"    {mark} {entry['name']:20s} {entry_actual:>10} / {entry_size:>10} {piece_info}")
    print(f"\n[*] Total: {total_actual} / {total_expected} bytes", "✅" if all_ok else "❌")
    return all_ok


def verify_construct3(expected, dest):
    total = 0
    missing = []
    for url in expected:
        sp = save_path_for(url, dest)
        if not sp:
            continue
        total += 1
        if not os.path.exists(sp):
            missing.append(os.path.relpath(sp, dest))
    present = total - len(missing)
    ok = len(missing) == 0
    print(f"    {'✅' if ok else '❌'} {present}/{total} file(s) present")
    if missing:
        print(f"    Missing (first 10 of {len(missing)}):")
        for m in missing[:10]:
            print(f"      {m}")
    return ok


# ---------------------------------------------------------------------------
# Boot phase — supports --auto-boot
# ---------------------------------------------------------------------------

def boot(url, dest, max_boot=60, headless=False, verbose=False,
         auto_boot=False, quiet_seconds=5.0, min_boot=10.0):
    os.makedirs(dest, exist_ok=True)
    proc, port = launch_chrome(headless=headless)
    print(f"[*] Chrome launched (pid {proc.pid})")

    if not wait_for_cdp(port):
        proc.terminate()
        sys.exit("ERROR: CDP port never opened.")

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as r:
        targets = json.loads(r.read())
    page = next((t for t in targets if t.get("type") == "page"), None)
    if not page:
        proc.terminate()
        sys.exit("ERROR: no page target.")

    client = CDPClient(page["webSocketDebuggerUrl"])
    client.send("Network.enable", {"maxTotalBufferSize": 200_000_000, "maxResourceBufferSize": 100_000_000})
    client.send("Page.enable")
    print(f"[*] Navigating to {url}")
    if auto_boot:
        print(f"[*] Auto-boot: stop after {quiet_seconds:.1f}s quiet, min {min_boot:.1f}s, hard cap {max_boot}s")
    else:
        print(f"[*] Fixed boot: capture for {max_boot}s")

    saved_count = 0
    pending = {}
    manifest_url = None
    manifest_engine = None
    game_base_url = None
    last_activity = time.time()
    boot_start = time.time()

    def handle(msg):
        nonlocal saved_count, manifest_url, manifest_engine, game_base_url, last_activity
        method = msg.get("method")
        params = msg.get("params", {})

        if method == "Network.responseReceived":
            rid = params.get("requestId")
            resp = params.get("response", {})
            req_url = resp.get("url", "")
            status = resp.get("status", 0)
            if req_url:
                _note_host(req_url)
                if req_url.endswith("/index.html") and game_base_url is None:
                    game_base_url = req_url.rsplit("/", 1)[0]
            # Only track saveable, successful requests. This prevents:
            #   • Analytics/beacons/long-polls (save_path_for returns None)
            #     from keeping `pending` non-empty forever
            #   • 404s and 5xx errors from being saved as fake asset files
            if 200 <= status < 300 and save_path_for(req_url, dest):
                pending[rid] = req_url

        elif method == "Network.loadingFinished":
            rid = params.get("requestId")
            req_url = pending.pop(rid, None)
            if not req_url:
                return
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
                saved_count += 1
                last_activity = time.time() 
                print(f"  [{saved_count:3d}] {os.path.relpath(sp, dest)[:65]:<65} ({len(data):>10} B)")
                if not manifest_url:
                    eng, murl = detect_engine(req_url)
                    if eng:
                        manifest_url = murl
                        manifest_engine = eng
            except Exception as e:
                print(f"  [!] save failed: {e}")
        elif method == "Network.loadingFailed":
            # Request was cancelled or failed — remove from pending so
            # auto-boot can detect true network idle
            rid = params.get("requestId")
            pending.pop(rid, None)
    
    client.send("Page.navigate", {"url": url})

    notified = False
    while time.time() - boot_start < max_boot:
        msg = client.read_event(timeout=0.5)
        if msg:
            handle(msg)
        if manifest_url and not notified:
            notified = True
            print(f"\n[*] Manifest detected: {manifest_engine}  →  {manifest_url}")
            print(f"[*] Continuing to capture supporting files...")

        if auto_boot:
            elapsed = time.time() - boot_start
            idle = time.time() - last_activity
            if saved_count > 0 and elapsed >= min_boot and idle >= quiet_seconds and not pending:
                print(f"\n[*] Auto-boot: network idle for {idle:.1f}s after {elapsed:.1f}s — stopping capture")
                break
                
    drain_end = time.time() + 2
    while time.time() < drain_end:
        msg = client.read_event(timeout=0.3)
        if not msg:
            break
        handle(msg)

    client.close()
    try:
        proc.terminate()
    except Exception:
        pass

    print(f"\n[*] Boot phase complete: {saved_count} file(s) captured")

    if not manifest_url and game_base_url:
        for candidate, eng in [("/data.json", "construct3"),
                               ("/archive/archive_files.json", "defold")]:
            if os.path.exists(os.path.join(dest, candidate.lstrip("/"))):
                manifest_url = game_base_url + candidate
                manifest_engine = eng
                print(f"[*] Manifest found on disk: {manifest_engine}  →  {manifest_url}")
                break

    return manifest_engine, manifest_url


# ---------------------------------------------------------------------------
# Local server
# ---------------------------------------------------------------------------

MIME = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript",
    ".json": "application/json", ".wasm": "application/wasm",
    ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp",
    ".webm": "video/webm", ".mp4": "video/mp4", ".ogv": "video/ogg",
    ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".wav": "audio/wav",
    ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
    ".woff": "font/woff", ".woff2": "font/woff2", ".otf": "font/otf",
    ".ttf": "font/ttf", ".ico": "image/x-icon", ".xml": "application/xml",
    ".txt": "text/plain; charset=utf-8",
    ".projectc": "application/octet-stream",
    ".arci": "application/octet-stream",
    ".arcd": "application/octet-stream",
    ".dmanifest": "application/octet-stream",
    ".der": "application/x-x509-ca-cert",
    ".data": "application/octet-stream",
    ".pck": "application/octet-stream",
}


class GameHandler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        return MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")

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
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Manifest-first Poki game downloader.")
    ap.add_argument("url")
    ap.add_argument("dest")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--max-boot", type=int, default=60,
                    help="Hard cap on boot seconds (default 60; use 180+ with --auto-boot for big games)")
    ap.add_argument("--auto-boot", action="store_true",
                    help="Stop capture when network goes idle instead of waiting the full --max-boot")
    ap.add_argument("--quiet-seconds", type=float, default=5.0,
                    help="Seconds of network silence before auto-boot stops (default 5)")
    ap.add_argument("--min-boot", type=float, default=10.0,
                    help="Minimum seconds to capture even if idle (default 10)")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-serve", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    print("=" * 60)
    print(f"  Phase 1: Boot & sniff ({args.max_boot}s max)")
    print("=" * 60)
    engine, manifest_url = boot(
        args.url, args.dest,
        max_boot=args.max_boot,
        headless=args.headless,
        verbose=args.verbose,
        auto_boot=args.auto_boot,
        quiet_seconds=args.quiet_seconds,
        min_boot=args.min_boot,
    )

    if not engine or not manifest_url:
        print("\n[!] No manifest detected. Traffic-capture fallback.")
        if not args.no_serve:
            serve(args.dest, port=args.port, open_browser=not args.no_open)
        return

    print("\n" + "=" * 60)
    print(f"  Phase 2: Enumerate ({engine})")
    print("=" * 60)

    if engine == "defold":
        expected, manifest_data = enumerate_defold(manifest_url, args.dest)
    elif engine == "construct3":
        expected, manifest_data = enumerate_construct3(manifest_url, args.dest)
    else:
        expected, manifest_data = None, None

    if not expected:
        print(f"[!] Enumerator failed for {engine}.")
        if not args.no_serve:
            serve(args.dest, port=args.port, open_browser=not args.no_open)
        return

    print(f"[*] Manifest declares {len(expected)} file(s)")

    print("\n" + "=" * 60)
    print("  Phase 3: Download missing")
    print("=" * 60)

    work = find_work(expected, args.dest)
    if not work:
        print("[*] Nothing missing.")
    else:
        print(f"[*] {len(work)} file(s) to download")
        download_missing(work, args.dest)

    print("\n" + "=" * 60)
    print("  Phase 4: Verify")
    print("=" * 60)

    if engine == "defold":
        verify_defold(manifest_data, manifest_url, args.dest)
    elif engine == "construct3":
        verify_construct3(expected, args.dest)

    if not args.no_serve:
        print("\n" + "=" * 60)
        print("  Phase 5: Serve")
        print("=" * 60)
        serve(args.dest, port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()