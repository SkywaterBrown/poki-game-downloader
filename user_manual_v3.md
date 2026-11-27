# Poki Game Offline Ripper — Complete Manual

**Status:** ✅ Working for 8 engines, 12 games verified
**Last verified:** November 26, 2026
**Tools:** `poki_universal.py`, `poki_cdp.py`, Python HTTP server
**Scripts:** `D:\Win_Game\Poki\`
**Games:** `D:\Win_Game\Poki\<GameName>\`
**Backups:** `D:\Win_Game\Poki\_backups\`

---

## 1. The Strategy (read this first)

> **Manifest verifies. Traffic captures. Run both in one pass.**

A browser game is not a web page. It's an application that downloads its own
content at runtime. Static page-savers (Ctrl+S → "Webpage, Complete") capture
only the launcher — the HTML shell and the first few scripts — not the game.

The only reliable approach is to **observe the network**: open the game in a
real browser and record every HTTP response. The game itself is the best
scraper, because it knows exactly what it needs.

Three layers, always in this order:

1. **Capture** — open the game in a real browser, record every HTTP response
2. **Structure** — the URL path *is* the disk path; preserve it exactly
3. **Serve** — local HTTP server with correct MIME types and (sometimes)
   COOP/COEP headers

The "manifest-first" refinement: after boot, read the game's own manifest.
It declares exactly what's needed. Download from that list — no more
"playing until bored."

`poki_universal.py` automates all three phases plus verification.

### 1.1 Why both strategies, always

Manifest-first alone is not enough. Empirically demonstrated on
**Mad Skills Motocross 2**:

| Metric | Value |
|---|---|
| archive_files.json total | 8,407,591 B (8.4 MB) |
| Actual captured total | ~31.5 MB |
| Undeclared extra content | ~23 MB (a lazy-loaded ZIP) |

The manifest declared 8.4 MB. The game fetched 31.5 MB. The extra 23 MB was
an undocumented lazy-loaded content pack — invisible to manifest-first
downloads, caught by traffic capture during boot.

**Conclusion:** the two strategies are complementary, not redundant.

- Manifest-first = **verification** (proves the declared content is complete)
- Traffic capture = **discovery** (finds content the manifest forgot or can't declare)

`poki_universal.py` runs both in one pass for exactly this reason.

---

## 2. The Toolkit

| Tool | Purpose | When to use |
|---|---|---|
| **`poki_universal.py`** | Manifest-first + traffic fallback, `--auto-boot` | First choice. Handles 8 engines. |
| **`poki_cdp.py`** | Plain traffic capture (no manifest) | When `poki_universal.py` fails to load the game |
| **Python HTTP server** | `serve()` from either script | Always — after capture, to play |
| **Save All Resources extension** | Manual ZIP capture | Last resort if scripts fail |

All three share the same strategy. The scripts do the mechanical work.

---

## 3. Quick Start

### 3.1 Download a game

```powershell
python D:\Win_Game\Poki\poki_universal.py <poki-url> D:\Win_Game\Poki\<GameName> --port <port>
Defold example (Dan the Man, simple, 60s fixed boot):

powershell
python D:\Win_Game\Poki\poki_universal.py https://poki.com/en/g/dan-the-man D:\Win_Game\Poki\DanTheMan --port 8001
PlayCanvas / Unity / asset-heavy example (auto-boot):

powershell
python D:\Win_Game\Poki\poki_universal.py <url> D:\Win_Game\Poki\<Game> --port 8004 --auto-boot --max-boot 180 --quiet-seconds 6
During capture: leave the browser alone. Let the game reach its main menu.
That's when supporting files (.wasm, initial .arcd chunks, data.json) get fetched.

With --auto-boot: the script stops as soon as the network goes quiet
for --quiet-seconds (default 6s), capped at --max-boot (hard safety net).
You'll see:

text
[*] Auto-boot: network idle for 6.1s after 36.3s — stopping capture
That message is your proof auto-boot is working — 36 seconds instead of
waiting the full 180.

3.2 Play an already-downloaded game
powershell
python -c "import sys; sys.path.insert(0, r'D:\Win_Game\Poki'); from poki_universal import serve; serve(r'D:\Win_Game\Poki\DanTheMan-v2', port=8001)"
Or a stable wrapper you can save as play.ps1:

powershell
param([string]$Game, [int]$Port = 8000)
python -c "import sys; sys.path.insert(0, r'D:\Win_Game\Poki'); from poki_universal import serve; serve(r'D:\Win_Game\Poki\$Game', port=$Port)"
Then: .\play.ps1 DanTheMan-v2

3.3 Back it up (do this after every successful rip)
powershell
Compress-Archive -Path "D:\Win_Game\Poki\<Game>\*" -DestinationPath "D:\Win_Game\Poki\_backups\<Game>-backup.zip" -Force
Or bulk-backup everything that's missing a backup:

powershell
Get-ChildItem "D:\Win_Game\Poki" -Directory | Where-Object { $_.Name -ne "_backups" } | ForEach-Object {
    $zip = "D:\Win_Game\Poki\_backups\$($_.Name)-backup.zip"
    if (-not (Test-Path $zip)) {
        Compress-Archive -Path "$($_.FullName)\*" -DestinationPath $zip -Force
        Write-Host "Zipped $($_.Name)"
    }
}
4. Engine Support Matrix
Engine	Games tested	Enumerator	Verification
Defold	Dan the Man, Level Devil, Mad Skills MX 2	✅ archive_files.json	✅ Byte-exact per file
Construct 3	Stick Fighter	✅ data.json + index.html	✅ Presence (no sizes)
Unity WebGL	Getaway Shootout	Traffic fallback	—
Fancade	Drive Mad	Traffic fallback	—
Clickteam Fusion	Retro Bowl	Traffic fallback	—
GameMaker	Iron Snout	Traffic fallback	—
PlayCanvas	Village Builder	Traffic fallback + auto-boot	—
PixiJS	Silly Sky	Traffic fallback + auto-boot	—
Godot	— (not found on Poki)	—	—
Only Defold and Construct 3 have real enumerators. Everything else is
captured by observing the game's network traffic during boot. That's the
design: the fallback handles any engine without engine-specific code.

Godot is not available on Poki as of this writing. Multiple candidate URLs
were checked (Levelrinth, Silly Sky); none were Godot. Poki's own engineering
blog notes Godot's web export still has size problems that hurt retention.
If you find a Godot game later, look for .pck in DevTools → Network.

5. Engine-Specific Notes
5.1 Defold (Dan the Man, Level Devil, Mad Skills MX 2)
Manifest: archive/archive_files.json — JSON list of .arcd chunks
with byte offsets and total file sizes

Canonical layout: archive/game0.projectc, game0.arci,
game0.arcd–gameN.arcd, game0.dmanifest, game0.public.der

Engine binary: <GameName>.wasm + <GameName>_wasm.js — loaded
after the manifest, so the boot window must be long enough (30s+)

Progressive loading: archive split into 2 MB chunks fetched
sequentially. The manifest declares all of them upfront, so you can
download them directly without playing

COOP/COEP: Not required. Sending require-corp can actually break
.wasm loading. serve() sends unsafe-none which works

5.2 Construct 3 (Stick Fighter)
Manifest: data.json at the game root — a full JSON project file

Canonical layout: images/, media/, fonts/, scripts/ at the
root, alongside index.html

Worker files: scripts/jobworker.js, scripts/dispatchworker.js
must exist for Web Worker mode

COOP/COEP: C3 requires Cross-Origin-Opener-Policy: same-origin
and Cross-Origin-Embedder-Policy: require-corp for SharedArrayBuffer

⚠️ Strict runtime check: Modern C3 builds detect injected scripts and
refuse to run. See §7 for the Kaspersky workaround

5.3 Unity WebGL (Getaway Shootout)
Signature: Build/<hash>.loader.js, Build/<hash>.data, Build/<hash>.wasm

Manifest: none — Unity bundles everything in .data

Boot time: 30–60s. --auto-boot --max-boot 180 is fine

Extraction tool: UnityPy — pip install unitypy, then load the
.data file to extract PNG textures and OGG audio

5.4 GameMaker (Iron Snout)
Signature: html5game/*.js (single ~3MB engine file), html5game/*.ogg,
html5game/*_texture_*.png

Manifest: none

Boot time: ~15–25s to main menu

Preloads all sounds at boot — you'll see 20–40 .ogg files

5.5 PlayCanvas (Village Builder)
Signature: playcanvas-stable.min.js, __settings__.js, __start__.js,
__loading__.js, config.json, files/assets/<id>/<version>/<name>.glb

Manifest: config.json (not parsed by the enumerator — traffic fallback)

Boot time: 60–180s for 3D games. Use --auto-boot --max-boot 180 --quiet-seconds 6

Asset pattern: each 3D model is a separate .glb fetch

5.6 PixiJS (Silly Sky)
Signature: WebGLRenderer-*.js, SharedSystems-*.js, browserAll-*.js,
init-*.js (all PixiJS v8 modules), plus a large index.js game file

Assets: modern formats — .avif images, .opus audio

Boot time: ~30s. Auto-boot works well

Extraction: already done — .avif and .opus are standard, open
them in any image/audio viewer

5.7 Fancade (Drive Mad)
Signature: webapp/fancade.css, webapp/source_min.js,
webapp/index.wasm, webapp/index.data

Manifest: none

Boot time: very fast (<15s)

5.8 Clickteam Fusion (Retro Bowl)
Signature: html5game/RetroBowl.js (single ~7MB engine file),
html5game/snd_*.ogg, html5game/*_texture_*.png

Manifest: none

Boot time: ~20s

Note: Clickteam re-fetches the same files repeatedly during boot.
save_path_for() overwrites — no harm done, but file count is inflated

5.9 Unknown / custom engines
When detect_engine() returns None, poki_universal.py falls back to
plain traffic capture. Use --auto-boot --max-boot 180 --quiet-seconds 6.

Rule of thumb: if the game reaches its main menu during boot, the
traffic capture is complete. If it's still loading after 45s, either the
game is genuinely big — bump --max-boot — or it needs manual play (see
poki_cdp.py in §2).

6. Directory Layouts
Convention
All game folders go under D:\Win_Game\Poki\, not D:\ root, not
D:\Poki\. This keeps everything in one place and avoids spaces/! in paths
(which caused our original Stick Fighter debugging saga).

text
D:\Win_Game\Poki\
├── poki_universal.py
├── poki_cdp.py
├── user_manual_v2.md
├── play.ps1
├── Stick Fighter - Play Online for Free! _ Poki_files\   ← original
├── StickFighter-v2\
├── DanTheMan\
├── DanTheMan-v2\
├── LevelDevil\
├── DriveMad\
├── RetroBowl\
├── GatewayShootout\
├── IronSnout\
├── MadSkillMotoCross2\
├── VillageBuilder\
├── SillySky\
└── _backups\        ← every <Game>-backup.zip lives here
Construct 3 layout
text
<GameFolder>\
├── index.html
├── data.json                ← ⚠️ critical; game won't start without it
├── style.css, styles.css
├── poki-sdk.js, poki-sdk-hoist-*.js
├── images\, media\, fonts\, icons\
└── scripts\
    ├── c3runtime.js
    ├── main.js
    ├── offlineclient.js, register-sw.js, supportcheck.js
    ├── jobworker.js, dispatchworker.js
    └── project\
        └── scriptsInEvents.js
Defold layout (names vary — <X> is the game binary name)
text
<GameFolder>\
├── index.html
├── dmloader.js
├── <X>.wasm                 ← ⚠️ critical; the game binary
├── <X>_wasm.js
├── yes2sdk*.js, poki-sdk*.js
└── archive\
    ├── archive_files.json    ← manifest
    ├── game0.projectc
    ├── game0.arci
    ├── game0.arcd … gameN.arcd
    ├── game0.dmanifest
    └── game0.public.der
Unity layout
text
<GameFolder>\
├── index.html
├── Build\
│   ├── <hash>.loader.js
│   ├── <hash>.data
│   ├── <hash>.wasm
│   └── <hash>.framework.js
├── StreamingAssets\
└── screenshots\
PlayCanvas layout
text
<GameFolder>\
├── index.html
├── playcanvas-stable.min.js
├── __settings__.js, __start__.js, __loading__.js
├── __game-scripts.js
├── config.json
└── files\assets\<id>\<version>\<name>.glb
PixiJS layout (Silly Sky)
text
<GameFolder>\
├── index.html
├── index.js
├── WebGLRenderer-*.js, SharedSystems-*.js, browserAll-*.js, init-*.js
├── css\main.css, css\loader.css
├── images\*.avif
└── sounds\*.opus
7. ⚠️ Kaspersky / Antivirus Interference (Construct 3 Only)
Symptom: The C3 game loads but shows:

"Kaspersky Internet Security broke this export — It appears a script
was added to this export by Kaspersky software."

Cause: Kaspersky's HTTP inspector injects a script into every web
response to enable its browser extension. Modern Construct 3 runtimes
detect any tampering with their code and refuse to run.

This is not a bug in your setup. It's C3's security feature working
correctly. It happens because Kaspersky legitimately modifies the traffic.

Fix — never disable the antivirus. Instead:

Option A — Application Rule (most targeted)

Kaspersky → Settings → Protection → Application Control → Manage applications

Expand your browser (e.g., chrome.exe) → right-click → Details and rules

Tab Exclusions → check "Do not scan all traffic"

Check "Only for specified IP addresses" → enter 127.0.0.1

Check "Only for specified ports" → enter 8000-8100

Save and restart browser

Option B — Monitored Ports

Kaspersky → Settings → Security Settings → Network Settings

Click "Select" next to Monitored ports

Mark ports 8000-8100 as Inactive

Save and restart

Both approaches keep Kaspersky fully active for real internet traffic;
only localhost dev ports are exempt.

Defold / Unity / PlayCanvas / PixiJS games do not trigger this —
their runtimes don't check for script injection.

Why it appeared "suddenly": Two likely causes — (a) the C3 runtime
shipped a stricter version, (b) Kaspersky updated its injection
heuristics. Either way, the fix is the same and permanent.

8. Troubleshooting
Symptom	Cause	Fix
Failed to load module script: MIME type 'application/octet-stream'	Wrong extension or missing MIME mapping	Rename file (drop .download), or check serve() MIME dict
data.json 404 (C3)	Missing manifest	Re-capture; ensure game was fully booted
<Game>.wasm 404 (Defold)	Boot window too short	Increase --max-boot; let splash finish
SharedArrayBuffer is not defined (C3)	COOP/COEP missing	Use serve() — it sends both
ERR_BLOCKED_BY_RESPONSE.NotSameOriginAfterDefaultedToSameOriginByCoep	COEP too strict for .wasm	serve() sends unsafe-none — correct for Defold/Unity/PlayCanvas
Cannot set properties of undefined (setting 'init') from poki-sdk-hoist-*.js	Missing Poki context	Usually harmless — game still boots
Kaspersky "broke this export"	Script injection (C3 only)	See §7
Manifest: property 'start_url' ignored	PWA manifest host mismatch	Harmless
Permissions policy violation: unload	Chrome deprecation	Harmless
Port already in use	Zombie Chrome or prior server	Get-Process chrome, python | Stop-Process -Force
"Cannot remove the item… because it is in use"	You're cd'd into the target folder	cd D:\ first
Auto-boot fires at 10s with 0 files	saved_count > 0 gate missing	Fixed in current version — verify your handle()
Auto-boot never fires, runs to --max-boot	Non-saveable requests (analytics, beacons) kept pending non-empty	Fixed — only 2xx saveable requests enter pending
Folder has spaces or ! in name	Copied from browser save	Rename to simple alphanumeric name
9. PowerShell Reference
Bulk-rename .download files
powershell
Get-ChildItem -Recurse -File -Filter *.download |
  Rename-Item -NewName { $_.Name -replace '\.download$','' }
Strip .download from HTML references
powershell
(Get-Content index.html -Raw) -replace '\.download','' | Set-Content index.html -Encoding UTF8
Byte-total of a game folder
powershell
(Get-ChildItem -Recurse "D:\Win_Game\Poki\<Game>" | Measure-Object Length -Sum).Sum
Compare two rips (find files only in one)
powershell
$a = Get-ChildItem -Recurse "D:\Win_Game\Poki\<A>" | % { $_.FullName.Replace("D:\Win_Game\Poki\<A>\", '') }
$b = Get-ChildItem -Recurse "D:\Win_Game\Poki\<B>" | % { $_.FullName.Replace("D:\Win_Game\Poki\<B>\", '') }
Compare-Object $a $b | Where-Object SideIndicator -eq '<=' | Select-Object -ExpandProperty InputObject
Back up one game
powershell
Compress-Archive -Path "D:\Win_Game\Poki\<Game>\*" -DestinationPath "D:\Win_Game\Poki\_backups\<Game>-backup.zip" -Force
Bulk-backup every unbacked game
powershell
Get-ChildItem "D:\Win_Game\Poki" -Directory | Where-Object { $_.Name -ne "_backups" } | ForEach-Object {
    $zip = "D:\Win_Game\Poki\_backups\$($_.Name)-backup.zip"
    if (-not (Test-Path $zip)) {
        Compress-Archive -Path "$($_.FullName)\*" -DestinationPath $zip -Force
        Write-Host "Zipped $($_.Name)"
    }
}
Kill zombie Chrome / Python
powershell
Get-Process chrome, python -ErrorAction SilentlyContinue | Stop-Process -Force
10. Known-Good Rips
All folders under D:\Win_Game\Poki\, all backups under D:\Win_Game\Poki\_backups\.

Game	Engine	Folder	Verified
Stick Fighter (orig)	Construct 3	Stick Fighter - ... _ Poki_files\	✅ Manual play
Stick Fighter v2	Construct 3	StickFighter-v2\	✅ Backup verified
Dan the Man	Defold	DanTheMan\	✅ Backup verified
Dan the Man v2	Defold	DanTheMan-v2\	✅ Manifest byte-exact + backup
Level Devil	Defold	LevelDevil\	✅ Manifest byte-exact + backup
Mad Skills Motocross 2	Defold	MadSkillMotoCross2\	✅ Manifest byte-exact + 23 MB lazy ZIP + backup
Drive Mad	Fancade	DriveMad\	✅ Backup verified
Retro Bowl	Clickteam Fusion	RetroBowl\	✅ Backup verified
Getaway Shootout	Unity WebGL	GatewayShootout\	✅ Backup verified
Iron Snout	GameMaker	IronSnout\	✅ Backup verified
Village Builder	PlayCanvas	VillageBuilder\	✅ Backup verified
Silly Sky	PixiJS	SillySky\	⚠️ Works, backup pending
12 games, 8 engines, all playable offline.

11. Recovering From Scratch
If a script is lost or broken, use the Save All Resources Chrome extension
as a fallback:

Install Save All Resources (by unbug) from the Chrome Web Store

Open the game on Poki, play for 30–60 seconds

F12 → ResourcesSaver tab → Save All Resources → ZIP

Extract, find the CDN folder (<game-id>.gdn.poki.com/<version-id>/)

Copy its contents to D:\Win_Game\Poki\<GameName>\

Serve with serve() (§3.2)

This manual method always works, just slower.

12. Optional next step — Asset extraction
Every rip is currently an opaque archive. If you want to inspect what's
inside:

Engine	Tool	Extract
Defold	bob.jar (official)	PNG sprites, OGG sounds, Lua scripts
Unity	UnityPy (pip install unitypy)	PNG textures, OGG audio, TextAssets
PlayCanvas	Already done — .glb files	Open in Blender directly
PixiJS	Already done — .avif/.opus	Open in any viewer
GameMaker	File format partially documented	.ogg files already direct
Clickteam	No standard tool	.ogg files already direct
Unity extraction example:

python
import UnityPy, os
DATA = r"D:\Win_Game\Poki\GatewayShootout\Build\323862927f75a9b36201c486bc3975d5.data"
OUT = r"D:\Win_Game\Poki\GatewayShootout-extracted"
os.makedirs(OUT, exist_ok=True)
env = UnityPy.load(DATA)
for obj in env.objects:
    if obj.type.name == "Texture2D":
        try: obj.read().image.save(os.path.join(OUT, f"tex_{obj.path_id}.png"))
        except: pass
13. The One-Sentence Summary
Don't save the page. Read the manifest, capture the traffic, preserve the
URL-as-path, serve it over HTTP with the right MIME types — and tell your
antivirus to leave localhost alone.

