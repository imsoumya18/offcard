# Developing ShotLoft

[![Build](https://img.shields.io/github/actions/workflow/status/imsoumya18/shotloft/build.yml?branch=main&label=build)](https://github.com/imsoumya18/shotloft/actions/workflows/build.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-008787)](https://www.python.org/)

ShotLoft is a desktop app made of four parts. User-facing docs are in the [README](README.md).

| Part | What it is |
|---|---|
| [`shotloft.py`](shotloft.py) | The app: opens the window and serves the page and its actions |
| [`ui/index.html`](ui/index.html) | The window's contents: one page of HTML, CSS and JavaScript |
| [`engine.py`](engine.py) | The engine: card detection, matching, copying, repairs, verify, eject, finding bracket sets. Standard library only, Python 3.8+ |
| [`hdr.py`](hdr.py) | HDR merge of one bracket set. Needs NumPy, rawpy (LibRaw) and Pillow, which the built app bundles |

## Run from source

```bash
pip install pywebview                 # once, for the native window (Mac and Windows)
pip install numpy rawpy pillow        # once, for HDR merge (the app says so if they're missing)
python3 shotloft.py            # open the app
python3 shotloft.py --browser  # open it in the browser instead
python3 shotloft.py --serve    # no window; print the URL and token (tests)
```

## How the app works

- **Local server.** A small HTTP server on `127.0.0.1` (random port) serves the page and a JSON API
  (`/api/state`, `/api/dest`, `/api/pick`, `/api/plan`, `/api/import`, `/api/verify`,
  `/api/eject`, `/api/trash`, `/api/reset`, and for HDR Merge `/api/hdr/folder`, `/api/hdr/pick`,
  `/api/hdr/scan`, `/api/hdr/sets`, `/api/hdr/merge`, `/api/reveal`).
  - Every request needs a secret token created at launch, and a `127.0.0.1` Host header, so other
    web pages and other machines can't drive it.
  - Long jobs run in a background thread. The engine reports progress to the page through
    `PROGRESS_HOOK`. HDR Merge (its scan and its merges) has its own job slot, so it can run while
    a card backs up. `/api/state` carries only a summary of it; the page fetches the sets and
    their previews once per scan from `/api/hdr/sets`.
  - HDR Merge refuses a folder on a memory card, since ShotLoft never writes to a card.
- **Views.** The page opens on a list of tools (`TOOLS` in `ui/index.html`); each tool is a view,
  selected by the URL hash (`#backup`, `#hdr`). A new tool is a new entry there, a view, and its
  API routes.
- **Window.** On macOS and Windows the page opens in a native window
  ([pywebview](https://pywebview.flowrl.com/), using the system web view: WebKit on Mac, Edge
  WebView2 on Windows). On Linux, or if that window can't start, it opens in the default browser
  and quits about 45 seconds after the page is closed.
- **Folder picker.** A native dialog everywhere: pywebview's in the window, otherwise AppleScript,
  PowerShell, `zenity` or `kdialog`. You can also paste a path.
- **Engine loading.** The app loads `engine.py` and `hdr.py` at start-up. Because of that, the app
  imports their modules itself (the engine's standard-library ones, NumPy, rawpy and Pillow), so
  PyInstaller packs them into the built app.
- **macOS builds** add `NSAppTransportSecurity → NSAllowsLocalNetworking` to `Info.plist` and are
  re-signed ad hoc. Without it, the window can't load the app's own `http://127.0.0.1` page; the
  setting allows local addresses only.
- **Colours.** Each one has a single job, and all are readable in light and dark mode:

  | Colour | Used for |
  |---|---|
  | Teal | structure: the main button, progress bars, links |
  | Orange | what needs attention: new files, warnings |
  | Green | success: already backed up, done, safe to format |
  | Red | errors only |

## How the engine works

- **Card detection.** A drive counts as a Sony card when it has a `DCIM` folder named like
  `100MSDCF` or `10161017` and a `PRIVATE/M4ROOT` folder. Drives are looked for in these places:
  - macOS: `/Volumes`
  - Linux: `/media`, `/run/media`, `/mnt`
  - Windows: drive letters
- **What's copied.**
  - Photos: `.ARW`, `.JPG` and `.HIF` from every `DCIM` subfolder.
  - Videos: `PRIVATE/M4ROOT/CLIP/*.MP4`, plus their `M01.XML` sidecar files.
  - Ignored: proxies, thumbnails and AVCHD.
- **Dates.**
  - Photos: EXIF `DateTimeOriginal`, read by a small built-in parser, so no exiftool is needed.
  - Videos: the `CreationDate` in Sony's XML file.
- **Duplicate check.** There is no database: the backup folder is scanned each run. Every card
  file is matched on its own, by size and a hash of three 64 KB samples (start, middle, end).
  Names and dates aren't used, so renamed files still match. Size alone isn't enough, because
  Sony's compressed RAW files are all the same size.
- **Pairs.** If only half of a video (`.MP4` + `.XML`) or a RAW + JPG photo is backed up, the
  missing half is copied next to the half that's there, under the same number. The exception: a
  JPG whose RAW is backed up counts as removed on purpose (the Trash option), so it isn't copied
  back.
- **Numbering.** New files continue from the highest `DSC#####` / `C#####` already in the backup.
  Orphan `.XML` files count too, so numbers never collide.
- **Free space.** Before copying, the needed bytes (plus a 50 MB margin) are compared with the free
  space on the backup drive.
- **Verify ("safe to format?").** Each card file is located in the backup by size and fingerprint,
  then compared in full, byte for byte. Each file comes out *verified*, *missing*, or *different*
  (a damaged copy). A JPG whose RAW is backed up but which is itself missing counts as trashed on
  purpose, and isn't a failure. The card is safe only when nothing is missing or different.
- **Copying.** Each file is written as `*.partial`, its size is checked, and then it's renamed into
  place. The original file timestamp is kept.
- **Trash.** Uses Finder on macOS and the Recycle Bin via PowerShell on Windows. That's refused on
  removable drives, which have no Recycle Bin. On Linux it uses `gio trash` or `trash-cli`.
- **Eject.**
  - macOS: `diskutil eject`.
  - Windows: the Shell "Eject" verb. It reports nothing, so the engine waits for the drive letter
    to disappear.
  - Linux: `gio mount -e` or `udisksctl`.
  
  It only acts on the top of a mounted drive (`os.path.ismount`), so it can never eject the drive a
  plain folder sits on. It never formats or deletes.
- **Update notice.** When the app starts, a background thread asks the GitHub API for the latest
  release, with a 3-second timeout.
  - It falls back to `curl` if Python can't verify HTTPS, and says nothing when offline.
  - If the release is newer than `__version__`, the app shows a banner with the update line.
  - Turn it off with `SHOTLOFT_NO_UPDATE_CHECK=1`.
- **Saved settings.** The backup folder is remembered in `~/.shotloft.json`.

### Engine commands (internal)

The engine also has commands with JSON output. They're used by the tests and by scripts (such as
a Claude skill that runs backups), and aren't part of the user-facing app:

```bash
python3 engine.py detect --dest "$DEST" --json           # cards, backup drive
python3 engine.py plan   --dest "$DEST" --json           # what would be copied
python3 engine.py import --dest "$DEST" --report r.json  # copy, write a JSON report
python3 engine.py verify --dest "$DEST" --json           # byte-for-byte check
python3 engine.py eject  [--card PATH]                   # safely eject the card(s)
python3 engine.py check-update --json                    # is a newer release out?
python3 engine.py trash-jpgs --report r.json             # move extra JPGs to the Trash
python3 engine.py brackets --folder "$DEST" --json       # bracket sets, subfolders too
python3 hdr.py merge OUT_DIR A.ARW B.ARW C.ARW [--tiff]  # merge one set (needs the HDR libraries)
```

- **Cards:** `--card PATH` (repeatable) picks specific cards. Otherwise every connected Sony card
  is used.
- **Backup folder:** `--dest` can come from the `SHOTLOFT_DEST` environment variable instead.
- **Exit codes:**

  | Code | Meaning |
  |---|---|
  | `0` | OK |
  | `1` | Some files failed (for `verify`: not safe to format) |
  | `2` | Bad arguments, or no card |
  | `3` | Not enough space on the backup drive (nothing copied) |

## How HDR merge works

**Finding sets** (`engine.find_brackets`, standard library). It reads every RAW file under the
chosen folder, subfolders included (not hidden or `HDR` folders). Sony writes each bracket frame's
exposure step into its EXIF (`ExposureBiasValue`), even in M mode. A set is consecutive RAW shots
in one folder (so copies of the same shots in two folders stay apart), at most 2 s apart, from the same camera at the same focal length, whose steps differ and span at
least 1 EV. A step already in the set starts the next set. Bursts and white-balance or DRO
brackets keep one exposure, so they never count. The result goes to
`<its folder>/HDR/DSC00012-00014_HDR.jpg`, and the backup index skips `HDR` folders, so merges are never
taken for backed-up files.

**Merging** (`hdr.py`). Every choice below was tested on real a6600 brackets (handheld, ISO 250 and
2500, ±2 and ±3 EV, a window brighter than the darkest frame, a curtain moving in the wind):

| Step | What it does | Why |
|---|---|---|
| Decode | LibRaw's AHD demosaic to linear camera RGB, full size; analysis on a 2×2-binned half-size copy | Linear data is what makes the merge simple maths |
| Clipping | A colour counts as clipped within 2.5% of white | Sony's lossy RAW smears the clip level by about ±100 |
| Noise | Fits variance = a·signal + b per frame, from the two green pixels of each Bayer block | They see the same light, so their difference is pure noise |
| Align | Phase correlation of 256 px tiles on exposure-equalised log luminance, then a robust affine fit (shift, rotation, scale) | Handheld frames moved up to ~9 px and 0.15°; a tile-by-tile local field was tried and didn't help |
| Exposure ratio | Measured from the pixels, on pixels chosen by the reference only | EXIF shutter speeds are rounded ("1/13" is really 1/12.5); choosing pixels by the noisy frame biases the ratio |
| Merge | Weights 1/variance, per pixel, fading out near a frame's clipped areas; per colour only where every frame is clipped somewhere | The statistically best estimate; mixing sources per colour caused colour speckle |
| Ghosts | A frame is left out where it differs from the reference by more than noise plus a 1.5 px misalignment at edges can explain. The reference is the middle exposure, or the next darker frame where it's clipped | Without the edge term, motion blur at edges was taken for movement and left noisy dots |
| Highlights | Colours clipped in every frame are rebuilt toward white | Never magenta |
| Tone | Mertens exposure fusion of virtual exposures of the merge, worked out at 1/4 size and applied as a smooth gain at full size, with saturation reduced as pixels are lifted (Mantiuk 2009) | Natural look without halos; the gain keeps full-size detail; lifted shadows don't turn garish |
| Finish | Defringe (violet edges next to very bright areas take their surroundings' colour), then a light blur on colour only | Lens purple fringing at windows; colour noise in lifted shadows |

About 30 s per 3-shot set of 24 MP on an Apple Silicon Mac, and about 2.5 GB of memory at peak
(about half of it LibRaw's decoding buffers). The optional TIFF is the merge with only a gentle
global roll-off, for editing.

## Tests

- **[`tests/smoke_test.py`](tests/smoke_test.py)** tests the engine. It builds a fake Sony card
  (tiny JPG/ARW files with real EXIF dates, a burst pair and a video), imports it, and checks the
  exact folder tree. Then it checks that:
  - a second run copies nothing
  - each half of a video or RAW + JPG pair deleted from the backup is put back under the same name
  - a deleted single photo comes back once
  - renamed files are still recognised
  - a JPG trashed on purpose isn't brought back
  - `verify` passes after an import, and catches both a backup copy with one byte changed (in a
    spot the quick fingerprint doesn't sample) and a missing backup file
  - a full backup drive stops the import before anything is copied
  - eject refuses a plain folder
  - a file moved into an `HDR` folder doesn't count as backed up
  - `brackets` searches subfolders, finds two bracket sets (with a burst between them that isn't
    one), keeps a copy of the same shots in another folder apart, names their output, and shows a
    set as merged once its file exists
  - the update check reports a newer release, ignores an older one, and stays quiet when offline
- **[`tests/app_test.py`](tests/app_test.py)** tests the app the way its page uses it:
  - choose a folder, check what's new, back up, verify, try to eject, then check again
  - requests with no token, a wrong token, or a foreign Host header are refused
  - HDR Merge: a folder on a card is refused, the backup folder is searched with its subfolders in
    the background, and a merge of fake RAW files fails cleanly
  - `--hdr-selftest`: the merge itself, inside that app (so a built app's bundled libraries are
    checked too), on synthetic frames: alignment, shadow noise, and a window recovered from the
    dark frame (`python3 hdr.py selftest` runs the same test from source)

```bash
python3 tests/smoke_test.py python3 engine.py      # the engine
python3 tests/app_test.py python3 shotloft.py    # the app, from source
python3 tests/app_test.py "dist/ShotLoft.app/Contents/MacOS/ShotLoft"   # a built Mac app
```

Test hooks:

| Variable | What it does |
|---|---|
| `SHOTLOFT_TEST_CARDS` | Treats these folders as plugged-in cards |
| `SHOTLOFT_TEST_FREE_BYTES` | Fakes the free space on the backup drive |
| `SHOTLOFT_UPDATE_URL` | Uses this URL for the update check |
| `SHOTLOFT_URL_FILE` | Writes the `--serve` URL to a file, for windowed builds without a console |

## Former name (Sony Import)

ShotLoft was called **Sony Import** up to v2.0.0. The old name appears in the code in exactly three
places, all for moving existing users over:
- **Settings** (`engine.py`): if `~/.shotloft.json` doesn't exist yet, `~/.sony-import.json` is
  read once, so the saved backup folder carries over.
- **Installers:**
  - Until the first ShotLoft release exists, they fall back to the last `sony-import-*` release
    files.
  - After installing ShotLoft, they remove the old Sony Import app, but only if it's ours:
    - Mac: checked by its bundle ID `io.github.imsoumya18.sony-import`.
    - Windows: its own `Programs\Sony Import` folder and Start-menu entry.
    - Linux: its menu entry.
- GitHub redirects the old repo address (`imsoumya18/sony-import`) and old install lines to
  `imsoumya18/shotloft`.

## The one-line installers

Files downloaded by `curl` or `Invoke-WebRequest` don't get the "downloaded from the internet"
mark. That's why the installed app opens without the Gatekeeper or SmartScreen warnings that
browser downloads hit. The real fix would be paid code signing; this avoids the warnings without
it.

### macOS and Linux: [`install.sh`](install.sh)

It downloads the latest release with `curl`:
- **macOS:** unpacks `ShotLoft.app` with `ditto`, keeping its signature. It installs into
  `/Applications`, or into `~/Applications` if that isn't writable, replacing an older version. It
  refuses while the app is open.
- **Linux:** installs `~/.local/bin/shotloft` (it opens in the browser) and an app-menu entry.

| Variable | Default |
|---|---|
| `SHOTLOFT_RELEASES` | `https://github.com/imsoumya18/shotloft/releases/latest/download` |
| `SHOTLOFT_RAW` | `https://raw.githubusercontent.com/imsoumya18/shotloft/main` (Linux icon) |
| `SHOTLOFT_APPS_DIR` | `/Applications` (macOS) |
| `SHOTLOFT_BIN_DIR` | `~/.local/bin` (Linux) |
| `SHOTLOFT_NO_REVEAL` | If unset, the app is shown in Finder afterwards |

### Windows: [`install.ps1`](install.ps1)

It runs as `irm …/install.ps1 | iex`, in Windows PowerShell 5.1 or later:
- It downloads `ShotLoft.exe` into `%LOCALAPPDATA%\Programs\ShotLoft`, which needs no admin
  rights, and adds a **ShotLoft** Start-menu shortcut.
- `Unblock-File` makes sure the app carries no "from the internet" mark.
- It runs inside `& { … }` and never calls `exit`, so a failure can't close the user's PowerShell
  window.

Overrides: `SHOTLOFT_RELEASES`, `SHOTLOFT_INSTALL_DIR` and `SHOTLOFT_START_MENU`.

The icons are [`docs/icon.png`](docs/icon.png) (1024 px), [`docs/AppIcon.icns`](docs/AppIcon.icns)
and [`docs/icon.ico`](docs/icon.ico), drawn in the app's teal and orange.

## Building and releasing

On every push, [GitHub Actions](.github/workflows/build.yml) runs these jobs:

| Job | What it does |
|---|---|
| `engine` | Engine tests from source, on Windows, macOS and Linux |
| `app` | Builds the app with PyInstaller for Windows, macOS (Apple Silicon and Intel) and Linux, and runs the app test against each build. The HDR libraries are pinned; Intel Macs get rawpy 0.25.1, its last release with Intel Mac wheels |
| `installer`, `installer-windows` | Install the app built in the same run with the one-line installers, then run the app test against the installed copy |
| `release` | Only for version tags, and only once all the others pass |

To publish a new version:
1. Add a `## [X.Y.Z] - date` section to [CHANGELOG.md](CHANGELOG.md), written for users. Usually
   you just rename `## [Unreleased]`.
2. Bump `__version__` in `engine.py`. The app shows it, and the update notice uses it.
3. Commit, then tag and push:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```

The release notes are that CHANGELOG section plus the install lines
([`.github/scripts/release-notes.sh`](.github/scripts/release-notes.sh)). If the section is
missing, the job falls back to GitHub's automatic notes and shows a warning. Badges can lag a few
minutes after a release, because the badge service and GitHub cache the image.
