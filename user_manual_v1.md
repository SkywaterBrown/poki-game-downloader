# Stick Fighter — Offline Setup Manual

**Status:** ✅ Working
**Last verified:** November 22, 2026
**Server:** Rebex Tiny Web Server
**URL:** `http://localhost:1180/StickFighter/index.html`

---

## 1. What This Is

A local, offline copy of the Poki browser game **Stick Fighter** (a Construct 3 / HTML5 game by ARF Games), served through Rebex Tiny Web Server. No internet required to play.

---

## 2. The Final Working Setup (TL;DR)

| Item | Value |
|---|---|
| Game folder | `D:\StickFighter\` |
| Server root | `D:\` (in `RebexTinyWebServer.exe.config`) |
| HTTP port | `1180` |
| Play URL | `http://localhost:1180/StickFighter/index.html` |
| Backup | `D:\StickFighter-backup.zip` |

**To play:** Start `RebexTinyWebServer.exe` → open the URL above in a browser.

---

## 3. Required Folder Structure

```
D:\StickFighter\
├── index.html                          ← entry point
├── data.json                           ← ⚠️ CRITICAL — Construct 3 project file
├── style.css
├── styles.css
├── en-us.json
├── palettes.json
├── movesets.json
├── chars.json
├── poki-sdk.js
├── poki-sdk-hoist-4fb6d95e3020d8b93152f378a8052cfe05e98f18.js
├── appmanifest.json                    (optional, PWA only)
├── fonts\
├── icons\
├── images\                             ← all sprites / textures
├── media\                              ← all sounds / music (.webm)
└── scripts\
    ├── c3runtime.js                    ← game engine
    ├── main.js
    ├── offlineclient.js
    ├── register-sw.js
    ├── supportcheck.js
    ├── jobworker.js                    ← Web Worker
    ├── dispatchworker.js               ← Web Worker
    └── project\
        └── scriptsInEvents.js
```

> **Key insight:** the game uses a `scripts/` subfolder structure, *not* a flat layout. Getting this structure right is what made it work.

---

## 4. How We Got Here (The Journey)

### ❌ What Did NOT Work

1. **Chrome → Save Page, Complete.** Captures only the DOM shell (`index.html`, `main.js`, etc.) plus ~200 junk files (Poki thumbnails, ad scripts, country flags). It **does not** capture files fetched by JavaScript at runtime — which is nearly the entire game (`data.json`, all assets).

2. **Double extensions.** Saved files came down as `main.js.download`. Browsers refuse to execute them.

3. **`file://` protocol.** Construct 3 games won't run from a local file — browsers block required features for security.

### ✅ What DID Work

1. **Save All Resources** (Chrome extension by *unbug*) → captured every network request into `poki.com.zip`.

2. Extracted the **CDN folder** (not the Poki wrapper):
   ```
   bb2ee878-98c6-4177-9e46-fbb00058ce0a.gdn.poki.com\
     0f61abb1-787f-4f8a-8264-f6a2a93f0ba2\
   ```
   This contains the *real* game with correct folder structure.

3. Copied the contents to `D:\StickFighter\`.

4. Renamed the two Poki SDK files to match what `index.html` expects (see §3).

5. Served through Rebex with a **clean URL** (no spaces, no `%20`, no `!`).

---

## 5. Rebex Configuration

File: `RebexTinyWebServer.exe.config` (sits next to the `.exe`)

Relevant settings:

```xml
<add key="httpPort" value="1180" />
<add key="webRootDir" value="D:\" />
<add key="defaultFile" value="index.html" />
```

> **Note:** Rebex is minimal — it doesn't ship with MIME mappings. It worked for us *because* the CDN files came down with correct extensions and Rebex handled `.js` / `.json` / `.webm` / `.png` correctly out of the box. If it ever stops serving a file type, check whether Rebex supports it.

---

## 6. Troubleshooting

### ❌ "Failed to load module script: MIME type of application/octet-stream"
Files have a `.download` suffix, or the HTML still references `.download` names.
- **Check:** look at the actual filenames in `D:\StickFighter\` and the URLs in the console error.
- **Fix:** rename files and strip `.download` from `index.html` references (see §8).

### ❌ 404 on `data.json`
`data.json` is missing from the game folder root. Without it, the runtime cannot start.
- **Fix:** re-download via *Save All Resources* and copy `data.json` from the CDN folder into `D:\StickFighter\`.

### ❌ 404 on `scripts/...` or `scripts/project/...`
Files are being fetched from a subfolder that doesn't exist, or they were flattened during a bad save.
- **Fix:** make sure the `scripts\` and `scripts\project\` folders exist with the correct files (§3).

### ❌ `SharedArrayBuffer is not defined` / COOP-COEP error
Construct 3's Web Worker requires specific HTTP headers Rebex won't send.
- **Fix (if it ever happens):** open `data.json`, look for a worker flag (`"useWorker"`, `"worker"`) and set it to `false`. Reload.

### ⚠️ `Manifest: property 'start_url' ignored...`
**Harmless.** Comes from `appmanifest.json` pointing at a Poki URL. Ignore.

### ⚠️ `Permissions policy violation: unload is not allowed`
**Harmless.** Chrome deprecation warning. Ignore.

### ⚠️ `poki-sdk-hoist-*.js ... Cannot set properties of undefined (setting 'init')`
**Harmless in practice.** The main `poki-sdk.js` still calls `measure()` successfully, and the game boots. Only worry if the game visibly stalls — then stub the SDK (see §9).

---

## 7. How to Rebuild From Scratch (Disaster Recovery)

If `D:\StickFighter\` is ever lost:

1. **Install** [Save All Resources](https://chrome.google.com/webstore) extension in Chrome.
2. **Open** `https://poki.com/en/g/stick-fighter` and **play for ~30 seconds** (menu → match → back). This ensures all assets load.
3. **DevTools** (`F12`) → **ResourcesSaver** tab → **Save All Resources**.
4. **Extract** the downloaded ZIP.
5. **Find** the CDN folder:
   ```
   bb2ee878-98c6-4177-9e46-fbb00058ce0a.gdn.poki.com\0f61abb1-787f-4f8a-8264-f6a2a93f0ba2\
   ```
6. **Copy** its contents to `D:\StickFighter\`:
   ```powershell
   Copy-Item -Path "D:\path\to\CDN\folder\*" -Destination "D:\StickFighter\" -Recurse -Force
   ```
7. **Rename** the two Poki SDK files (see §3):
   - `poki-sdk-hoist-*.js` → `poki-sdk-hoist-4fb6d95e3020d8b93152f378a8052cfe05e98f18.js`
   - `scripts\v2\poki-sdk.js` → `poki-sdk.js` (root)
8. **Restart Rebex** and load the URL.

---

## 8. Useful PowerShell Snippets

### Bulk-rename `.download` files
```powershell
Get-ChildItem -Recurse -File -Filter *.download |
  Rename-Item -NewName { $_.Name -replace '\.download$','' }
```

### Strip `.download` from HTML references
```powershell
(Get-Content index.html -Raw) -replace '\.download','' | Set-Content index.html -Encoding UTF8
```

### Find the CDN folder inside the ZIP extract
```powershell
Get-ChildItem -Path "D:\poki-extract" -Directory -Recurse |
  Where-Object { $_.Name -match '^0f61abb1' } |
  Select-Object -ExpandProperty FullName
```

### Back up the working install
```powershell
Compress-Archive -Path "D:\StickFighter\*" -DestinationPath "D:\StickFighter-backup.zip" -Force
```

### List the whole game folder with sizes
```powershell
Get-ChildItem -Recurse -Force D:\StickFighter |
  Select-Object @{N='Type';E={if($_.PSIsContainer){'DIR'}else{'FILE'}}},
                @{N='Size';E={if($_.PSIsContainer){''}else{$_.Length}}},
                FullName |
  Format-Table -AutoSize
```

---

## 9. Last-Resort Poki SDK Stub (Only If Needed)

If the game ever hangs on Poki SDK errors, add this **before** `<script src="./poki-sdk.js">` in `index.html`:

```html
<script>
window.PokiSDK = window.PokiSDK || {
  init: () => Promise.resolve(),
  gameLoadingFinished: () => {},
  gameLoadingProgress: () => {},
  commercialBreak: () => Promise.resolve(),
  rewardedBreak: () => Promise.resolve(false),
  measure: () => {},
  setDebug: () => {},
};
</script>
```

> **Only do this if the game actually stalls.** The current setup works without it — adding it unnecessarily risks breaking the working `measure()` call.

---

## 10. Everyday Usage Cheat Sheet

| Task | Action |
|---|---|
| Play | Start `RebexTinyWebServer.exe` → open `http://localhost:1180/StickFighter/index.html` |
| Stop | Close Rebex window |
| Back up | Run the `Compress-Archive` snippet in §8 |
| Restore | Extract `StickFighter-backup.zip` into `D:\` |
| Move install | Copy `D:\StickFighter\` anywhere; update URL path accordingly |
| Enable auto-start | Set `<add key="autoStart" value="true" />` in Rebex config |

---

## 11. Why It Works (Short Version)

- **Construct 3 games are dynamic** — they fetch `data.json` and all assets at runtime. Static page-savers miss all of it.
- **Folder structure matters** — the engine expects `scripts/`, `images/`, `media/`, `fonts/`, `icons/` as siblings of `index.html`.
- **Extensions matter** — browsers refuse to execute `.js` files served with the wrong MIME type or named `.js.download`.
- **Clean URLs matter** — spaces and `!` break path mapping on minimal servers. Use `D:\StickFighter\`, not the original Poki save folder name.
- **A local web server is mandatory** — `file://` blocks the features Construct 3 needs.

---




## Dan the Man (Defold engine)

**Command:**
    python D:\Win_Game\Poki\poki_cdp.py https://poki.com/en/g/dan-the-man D:\DanTheMan --wait 300

**Critical:** Actually play during the capture window.
- Splash loads `.wasm`
- First match loads `game0`–`game1.arcd`
- Each new level loads `game2`, `game3`, ...

**Minimum capture checklist:**
- DanTheManDefold.wasm present (~2.6 MB)
- archive/game0.arcd through game5.arcd present
- DanTheManDefold_wasm.js is exactly 293800 B

**Serve:**
    python -c "import sys; sys.path.insert(0, r'D:\Win_Game\Poki'); from poki_cdp import serve; serve(r'D:\DanTheMan')"

**URL:** http://localhost:8000/index.html
*End of manual.*