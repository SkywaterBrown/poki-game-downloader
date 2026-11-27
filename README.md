# Poki Game Offline Downloader

Download and play Poki.com browser games completely offline. 

*Concept & Idea by SkywaterBrown | Code generated with Deepseek*

## 🧠 The Strategy
Browser games aren't static web pages; they are applications that fetch their own assets at runtime. Standard "Save Page" tools only capture the launcher, not the game. 

This tool uses a dual-strategy approach to guarantee a complete offline rip:
1. **Traffic Capture (CDP):** Launches a headless Chrome instance via Chrome DevTools Protocol to sniff and save every HTTP response (catching lazy-loaded assets).
2. **Manifest Verification:** Parses engine-specific manifests (like Defold's `archive_files.json` or C3's `data.json`) to verify completeness and download any missing chunks.
3. **Local Serving:** Serves the captured files via a local Python HTTP server with the exact MIME types and COOP/COEP headers required by modern game engines.

## 🎮 Supported Engines
| Engine | Example Games | Method |
| :--- | :--- | :--- |
| **Defold** | Dan the Man, Level Devil, Mad Skills MX 2 | Manifest + Traffic |
| **Construct 3** | Stick Fighter | Manifest + Traffic |
| **Unity WebGL** | Getaway Shootout | Traffic Capture |
| **PlayCanvas** | Village Builder | Traffic Capture + Auto-boot |
| **GameMaker** | Iron Snout | Traffic Capture |
| **Fancade** | Drive Mad | Traffic Capture |
| **Clickteam** | Retro Bowl | Traffic Capture |
| **PixiJS** | Silly Sky | Traffic Capture + Auto-boot |

## ⚙️ Requirements
- **Python 3.x**
- **Google Chrome** or **Microsoft Edge** installed
- **websocket-client** library:
```bash
  pip install websocket-client
```

## 🚀 Quick Start

### 1. Download a Game (Recommended)
Use `poki_universal.py` for the manifest-first approach with traffic fallback.

```bash
# Standard download (e.g., Defold games)
python poki_universal.py https://poki.com/en/g/dan-the-man ./DanTheMan --port 8001

# Heavy 3D games (Unity/PlayCanvas) - use auto-boot to stop when network idles
python poki_universal.py <url> ./GameName --port 8002 --auto-boot --max-boot 180 --quiet-seconds 6
```
*Note: Leave the browser alone during the boot phase so the game can reach its main menu and fetch all initial assets.*

### 2. Download via Pure Traffic Capture
If the universal script fails to detect a manifest, use `poki_cdp.py` for a raw network capture.

```bash
python poki_cdp.py https://poki.com/en/g/<game> ./GameName --wait 120
```

### 3. Play Offline
Both scripts automatically start a local server and open your browser when finished. To play an already downloaded game later:

```bash
python -c "import sys; from poki_universal import serve; serve('./GameName', port=8001)"
```

## ⚠️ Important Notes & Troubleshooting

- **Antivirus Interference (Construct 3):** Modern C3 runtimes detect script injection and will refuse to run if Kaspersky or similar AV modifies localhost traffic. **Fix:** Whitelist `127.0.0.1` and ports `8000-8100` in your AV's network settings.
- **Folder Names:** Avoid spaces or `!` in your destination folder paths to prevent URL encoding issues.
- **Missing `.wasm` files:** If the game binary (`.wasm`) is missing, your `--max-boot` or `--wait` time was too short. The game needs time to finish its splash screen.
- **SharedArrayBuffer Errors:** Ensure you are using the built-in `serve()` function, as it injects the required `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` headers.

## 📄 License
This project is licensed under the MIT License.
