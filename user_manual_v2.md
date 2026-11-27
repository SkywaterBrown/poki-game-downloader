# Poki Game Offline Ripper — User Manual v2

**Status:** ✅ Working for 7 engines
**Last verified:** November 26, 2026
**Tools:** `poki_universal.py`, `poki_cdp.py`, Rebex Tiny Web Server
**Known-good games:** Stick Fighter, Dan the Man, Level Devil, Drive Mad, Retro Bowl,
Getaway Shootout, Iron Snout, Mad Skills Motocross 2, Village Builder

---

## 1. The Strategy (read this first)

> **Manifest verifies. Traffic captures. Run both in one pass.**

A browser game is not a web page. It's an application that downloads its own content at runtime. Static page-savers capture only the launcher, not the game. The only reliable approach is to observe the network — the game itself is the best scraper.

Three layers, always in this order:

1. **Capture** — open the game in a real browser, watch every HTTP response
2. **Structure** — the URL path *is* the disk path; preserve it exactly
3. **Serve** — local HTTP server with correct MIME types and (sometimes) COOP/COEP headers

The "manifest-first" refinement: after boot, read the game's own manifest file. It declares exactly what's needed. Download from that list instead of "playing until bored."

`poki_universal.py` automates all three phases plus verification.

### 1.1 Why both strategies, always

Manifest-first alone is not enough. Empirically demonstrated on Mad Skills Motocross 2:

| Metric | Value |
|---|---|
| archive_files.json total | 8,407,591 B (8.4 MB) |
| Actual captured total | ~31.5 MB |
| Undeclared extra content | ~23 MB (a lazy-loaded ZIP) |

The manifest declared 8.4 MB. The game fetched 31.5 MB. The extra 23 MB
was an undocumented lazy-loaded content pack — invisible to manifest-first
downloads, caught by traffic capture during boot.

**Conclusion:** the two strategies are complementary, not redundant.
- Manifest-first = **verification** (proves the declared content is complete)
- Traffic capture = **discovery** (finds content the manifest forgot or couldn't declare)

`poki_universal.py` runs both in one pass for exactly this reason.

---

## 2. The Toolkit

| Tool | Purpose | When to use |
|---|---|---|
| **`poki_universal.py`** | Manifest-first downloader (8 engines, `--auto-boot`) | First choice. Fastest, verified. |
| **`poki_cdp.py`** | Generic traffic capture via CDP | Unknown engines, or when manifest fails |
| **Rebex Tiny Web Server** | Minimal static HTTP server | Optional; only if you prefer it over Python's |
| **Save All Resources extension** | Manual ZIP capture | Backup path if scripts fail |

All three methods share the same underlying strategy. The scripts do the mechanical work; the strategy is what matters.

---

## 3. Quick Start

### 3.1 Download a game

```powershell
python D:\Win_Game\Poki\poki_universal.py <poki-url> <dest-folder> --port <port>
```

Example (Defold — Dan the Man):
```powershell
python D:\Win_Game\Poki\poki_universal.py https://poki.com/en/g/dan-the-man D:\DanTheMan-v2 --port 8001
```

Example (Construct 3 — Stick Fighter):
```powershell
python D:\Win_Game\Poki\poki_universal.py https://poki.com/en/g/stick-fighter D:\StickFighter-v2 --port 8002
```
**For slow-loading games (3D, Unity, PlayCanvas):**
```powershell
python D:\Win_Game\Poki\poki_universal.py <url> D:\Poki\<Game> --port <port> --auto-boot --max-boot 180 --quiet-seconds 6
```
**During the `--max-boot` window (default 60s): leave the browser alone.** Let the game boot to the main menu. That's when supporting files (`.wasm`, initial `.arcd` chunks, `data.json`) get fetched.


When the script finishes, it serves the game automatically and opens a browser tab.

### 3.2 Play an already-downloaded game

```powershell
python -c "import sys; sys.path.insert(0, r'D:\Win_Game\Poki'); from poki_universal import serve; serve(r'D:\DanTheMan-v2', port=8001)"
```

Or with Rebex: point `webRootDir` at `D:\` and hit `http://localhost:1180/<GameFolder>/index.html`.

### 3.3 Back it up (do this after every successful rip)

```powershell
Compress-Archive -Path "D:\DanTheMan-v2\*" -DestinationPath "D:\DanTheMan-v2-backup.zip" -Force
```

---

## 4. Engine Support

| Engine | Games tested | Enumerator | Verification |
|---|---|---|---|
| **Defold** | Dan the Man, Level Devil, Mad Skills MX 2 | ✅ `archive_files.json` | ✅ Byte-exact per file |
| **Construct 3** | Stick Fighter | ✅ `data.json` + `index.html` | ✅ Presence (no sizes in manifest) |
| **Unity WebGL** | Getaway Shootout | Traffic fallback | — |
| **Fancade** | Drive Mad | Traffic fallback | — |
| **Clickteam Fusion** | Retro Bowl | Traffic fallback | — |
| **GameMaker** | Iron Snout | Traffic fallback | — |
| **PlayCanvas** | Village Builder | Traffic fallback + auto-boot | — |
| **Godot** | — (Levelrinth unconfirmed) | Not tested | — |

**Only Defold and Construct 3 have actual enumerators.** Everything else
captures the game's own network requests during boot. That's the design:
the fallback handles any engine without needing engine-specific code.

---

## 5. Engine-Specific Notes

### 5.1 Construct 3 (Stick Fighter)

- **Manifest:** `data.json` at the game root — a full JSON project file
- **Canonical layout:** `images/`, `media/`, `fonts/`, `scripts/` at the root, alongside `index.html`
- **Worker files:** C3 uses Web Workers by default. `jobworker.js` and `dispatchworker.js` must live under `scripts/`
- **COOP/COEP:** C3 *requires* `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` for SharedArrayBuffer
- **⚠️ Strict runtime check:** Modern C3 builds **detect injected scripts** and refuse to run. See §7 (Kaspersky)

### 5.2 Defold (Dan the Man)

- **Manifest:** `archive/archive_files.json` — a JSON list of `.arcd` chunks with byte offsets
- **Canonical layout:** `archive/game0.projectc`, `game0.arci`, `game0.arcd`–`gameN.arcd`, `game0.dmanifest`, `game0.public.der`
- **Progressive loading:** Defold splits the archive into 2 MB chunks fetched sequentially. The manifest declares all of them upfront, so **you can download them directly without playing**
- **Engine binary:** `DanTheManDefold.wasm` + `DanTheManDefold_wasm.js` — loaded *after* the manifest, so boot window must be long enough
- **COOP/COEP:** *Not required* (and can break `.wasm` loading if enabled incorrectly)

### 5.3 Unknown engines

When `detect_engine()` returns `None`, `poki_universal.py` falls back to plain traffic capture for the `--max-boot` window and skips Phase 2/4. Use `poki_cdp.py` directly for more control (custom `--wait`, `--interactive`).

### 5.4 Unknown / custom engines

When `detect_engine()` returns `None`, `poki_universal.py` falls back to
plain traffic capture during the `--max-boot` window. No verification is
possible (there's no manifest), but the game is fully captured.

Tested working:
- Fancade (Drive Mad) — 11 files, custom WASM+data packing
- Clickteam Fusion (Retro Bowl) — 81 files, single-file 7MB JS engine

**Rule of thumb:** if `--max-boot 45` shows the game reaching its main menu,
the fallback capture is complete. If it's still loading after 45s, bump to
`--max-boot 90` or `--max-boot 120`.

### 5.5 GameMaker (Iron Snout)

- **Signature:** `html5game/*.js` (single large engine file), `html5game/*.ogg`, `html5game/*.png` texture sheets
- **Manifest:** none — traffic capture only
- **Boot time:** ~15-25s to main menu
- **Warning:** GameMaker games preload all sounds at boot; you'll see 20–40 `.ogg` files
- **PlayCanvas note:** GameMaker and PlayCanvas both have no manifest. If the game reaches
  its menu during `--max-boot 45`, that's enough.

### 5.6 PlayCanvas (Village Builder)

- **Signature:** `playcanvas-stable.min.js`, `__settings__.js`, `__start__.js`, `__loading__.js`, `config.json`, `files/assets/<id>/<version>/<name>.glb`
- **Manifest:** `config.json` (but the enumerator doesn't parse it yet — traffic fallback is sufficient)
- **Boot time:** 60–180s for asset-heavy 3D games; use `--auto-boot --max-boot 180`
- **Asset pattern:** each 3D model is a separate `.glb` fetch. A complex 3D game can pull 100+ assets.
---

## 6. Directory Layouts

### Directory Convention

**All game folders go under `D:\Poki\`**, not `D:\` root:
```
D:\Poki
├── StickFighter
├── DanTheMan-v2
├── LevelDevil
├── DriveMad
├── RetroBowl
├── GatewayShootout
├── IronSnout
├── MadSkillMotoCross2
├── VillageBuilder
└── _backups\ ← all .zip backups here
```

**Why:** keeps `D:\` root clean, and avoids spaces/`!` in paths (which caused
our original Stick Fighter debugging saga). `D:\Poki\StickFighter\` > `D:\Stick Fighter - Play Online for Free! _ Poki_files\`.


### Construct 3
```
<GameFolder>\
├── index.html
├── data.json                ← ⚠️ critical; game won't start without it
├── style.css
├── poki-sdk.js
├── poki-sdk-hoist-*.js
├── images\
├── media\
├── fonts\
├── icons\
└── scripts\
    ├── c3runtime.js
    ├── main.js
    ├── offlineclient.js
    ├── register-sw.js
    ├── supportcheck.js
    ├── jobworker.js
    ├── dispatchworker.js
    └── project\
        └── scriptsInEvents.js
```

### Defold
```
<GameFolder>\
├── index.html
├── dmloader.js
├── DanTheManDefold.wasm         ← ⚠️ critical; the game binary
├── DanTheManDefold_wasm.js
├── yes2sdk*.js
├── poki-sdk*.js
├── Y2G_Splash.png
└── archive\
    ├── archive_files.json        ← manifest
    ├── game0.projectc
    ├── game0.arci
    ├── game0.arcd … game5.arcd
    ├── game0.dmanifest
    └── game0.public.der
```

---

## 7. ⚠️ Kaspersky / Antivirus Interference (Construct 3 Only)

**Symptom:** The C3 game loads but shows:
> *"Kaspersky Internet Security broke this export — It appears a script was added to this export by Kaspersky software."*

**Cause:** Kaspersky's HTTP inspector injects a script into every web response to enable its browser extension. Modern Construct 3 runtimes detect any tampering with their code and refuse to run.

**This is not a bug in your setup.** It's C3's security feature working correctly. It happens because Kaspersky legitimately modifies the traffic.

**Fix — never disable the antivirus.** Instead:

**Option A — Application Rule (most targeted)**
1. Kaspersky → **Settings** → **Protection** → **Application Control** → **Manage applications**
2. Expand your browser (e.g., `chrome.exe`) → right-click → **Details and rules**
3. Tab **Exclusions** → check **"Do not scan all traffic"**
4. Check **"Only for specified IP addresses"** → enter `127.0.0.1`
5. Check **"Only for specified ports"** → enter the port range (e.g., `8000-8100`)
6. Save and restart browser

**Option B — Monitored Ports**
1. Kaspersky → **Settings** → **Security Settings** → **Network Settings**
2. Click **"Select"** next to *Monitored ports*
3. Mark ports `8000-8100` as **Inactive**
4. Save and restart

Both approaches keep Kaspersky fully active for real internet traffic; only localhost dev ports are exempt.

**Defold games do not trigger this** — Defold's runtime doesn't check for script injection.

**Why it appeared "suddenly":** Two likely causes — (a) the C3 runtime shipped a stricter version, (b) Kaspersky updated its injection heuristics. Either way, the fix is the same and permanent.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Failed to load module script: MIME type 'application/octet-stream'` | Wrong extension or missing MIME mapping | Rename file (drop `.download`), or check `serve()` MIME dict |
| `data.json` 404 (C3) | Missing manifest | Re-capture; ensure game was fully booted during capture |
| `DanTheManDefold.wasm` 404 (Defold) | Boot window too short | Increase `--max-boot`; let splash finish before touching browser |
| `SharedArrayBuffer is not defined` (C3) | COOP/COEP missing | `serve()` sends them; if using Rebex, headers won't be present — switch to Python server |
| `ERR_BLOCKED_BY_RESPONSE.NotSameOriginAfterDefaultedToSameOriginByCoep` | COEP too strict for `.wasm` | COEP must be `unsafe-none` for Defold; `require-corp` for C3 |
| `Cannot set properties of undefined (setting 'init')` from `poki-sdk-hoist-*.js` | Missing Poki context | Usually harmless — game still boots |
| Kaspersky "broke this export" | Script injection (C3 only) | See §7 |
| `Manifest: property 'start_url' ignored` | PWA manifest host mismatch | Harmless; ignore |
| `Permissions policy violation: unload` | Chrome deprecation | Harmless; ignore |
| Port already in use | Zombie Chrome or prior server | `Get-Process chrome, python \| Stop-Process -Force` |
| "Cannot remove the item… because it is in use" | You're `cd`'d into the target folder | `cd D:\` first |
| Auto-boot never fires; runs to `--max-boot` | Background XHR polling keeps `last_activity` fresh | Only count file saves as activity (see code fix in handle()) |
| Folder has spaces or `!` in name | Copied from a browser save | Rename to simple alphanumeric name under `D:\Poki\` |

---

## 9. PowerShell Reference

### Bulk-rename `.download` files
```powershell
Get-ChildItem -Recurse -File -Filter *.download |
  Rename-Item -NewName { $_.Name -replace '\.download$','' }
```

### Strip `.download` from HTML references
```powershell
(Get-Content index.html -Raw) -replace '\.download','' | Set-Content index.html -Encoding UTF8
```

### Byte-total of a game folder
```powershell
(Get-ChildItem -Recurse <Folder> | Measure-Object Length -Sum).Sum
```

### Compare two rips
```powershell
$a = Get-ChildItem -Recurse <FolderA> | % { $_.FullName.Replace((Resolve-Path <FolderA>).Path + '\','') }
$b = Get-ChildItem -Recurse <FolderB> | % { $_.FullName.Replace((Resolve-Path <FolderB>).Path + '\','') }
Compare-Object $a $b | Where-Object SideIndicator -eq '<=' | Select-Object -ExpandProperty InputObject
```

### Back up
```powershell
Compress-Archive -Path "<Folder>\*" -DestinationPath "<Folder>-backup.zip" -Force
```

### Kill zombie Chrome / Python
```powershell
Get-Process chrome,python -ErrorAction SilentlyContinue | Stop-Process -Force
```

```powershell
# Bulk zip all unbackuped games
Get-ChildItem D:\Poki -Directory | Where-Object {
    -not (Test-Path "D:\Poki\_backups\$($_.Name)-backup.zip")
} | ForEach-Object {
    Compress-Archive -Path "$($_.FullName)\*" `
        -DestinationPath "D:\Poki\_backups\$($_.Name)-backup.zip" -Force
    Write-Host "Zipped $($_.Name)"
}
```
```powershell
# Migrate from D:\ root to D:\Poki
$games = @("StickFighter","DanTheMan","DanTheMan-v2","StickFighter-v2",
           "LevelDevil","DriveMad","RetroBowl","GatewayShootout",
           "IronSnout","MadSkillMotoCross2","VillageBuilder")
New-Item -ItemType Directory -Force -Path "D:\Poki" | Out-Null
New-Item -ItemType Directory -Force -Path "D:\Poki\_backups" | Out-Null
foreach ($g in $games) {
    if (Test-Path "D:\$g")          { Move-Item "D:\$g" "D:\Poki\$g" }
    if (Test-Path "D:\$g-backup.zip") { Move-Item "D:\$g-backup.zip" "D:\Poki\_backups\" }
}
```
---

## 10. Known-Good Rips

All folders under `D:\Poki\`, all backups under `D:\Poki\_backups\`.

| Game | Engine | Folder | Verified |
|---|---|---|---|
| Stick Fighter (orig) | Construct 3 | `D:\Win_Game\Poki\Stick Fighter - ...\` | ✅ Manual play |
| Stick Fighter v2 | Construct 3 | `D:\Poki\StickFighter-v2` | ✅ Backup verified |
| Dan the Man | Defold | `D:\Poki\DanTheMan` | ✅ Backup verified |
| Dan the Man v2 | Defold | `D:\Poki\DanTheMan-v2` | ✅ Manifest byte-exact + backup |
| Level Devil | Defold | `D:\Poki\LevelDevil` | ✅ Manifest byte-exact + backup |
| Mad Skills Motocross 2 | Defold | `D:\Poki\MadSkillMotoCross2` | ✅ Manifest byte-exact + 23 MB lazy zip + backup |
| Drive Mad | Fancade | `D:\Poki\DriveMad` | ✅ Traffic fallback + backup |
| Retro Bowl | Clickteam Fusion | `D:\Poki\RetroBowl` | ✅ Traffic fallback + backup |
| Getaway Shootout | Unity WebGL | `D:\Poki\GatewayShootout` | ✅ Traffic fallback + backup |
| Iron Snout | GameMaker | `D:\Poki\IronSnout` | ✅ Backup verified |
| Village Builder | PlayCanvas | `D:\Poki\VillageBuilder` | ✅ Backup verified |
| Levelrinth | Godot (unconfirmed) | — | ⚠️ Automated capture failed |
---

## 11. Recovering From Scratch

If a script is lost or broken, use the **Save All Resources** extension as a fallback:

1. Install the extension in Chrome
2. Open the game on Poki, play for 30–60 seconds
3. F12 → **ResourcesSaver** tab → **Save All Resources** → ZIP
4. Extract, find the CDN folder (`<game-id>.gdn.poki.com/<version-id>/`)
5. Copy its contents to your destination
6. Serve with `serve()` or Rebex

This manual method always works, just slower.

---

## 12. The One-Sentence Summary

**Don't save the page. Read the manifest, capture the traffic, preserve the URL-as-path, serve it over HTTP with the right MIME types — and tell your antivirus to leave localhost alone.**

---

*End of manual v2.*
