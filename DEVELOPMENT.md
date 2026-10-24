# Developing Sony Import

[![Build](https://img.shields.io/github/actions/workflow/status/imsoumya18/sony-import/build.yml?branch=main&label=build)](https://github.com/imsoumya18/sony-import/actions/workflows/build.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-008787)](https://www.python.org/)

Sony Import is a desktop app made of three parts. User-facing docs are in the [README](README.md).

| Part | What it is |
|---|---|
| [`sony-import-app.py`](sony-import-app.py) | The app: opens the window and serves the page and its actions |
| [`ui/index.html`](ui/index.html) | The window's contents: one page of HTML, CSS and JavaScript |
| [`sony-import.py`](sony-import.py) | The engine: card detection, matching, copying, repairs, verify, eject. Standard library only, Python 3.8+ |

## Run from source

```bash
pip install pywebview                 # once, for the native window (Mac and Windows)
python3 sony-import-app.py            # open the app
python3 sony-import-app.py --browser  # open it in the browser instead
python3 sony-import-app.py --serve    # no window; print the URL and token (tests)
```

## How the app works

- **Local server.** A small HTTP server on `127.0.0.1` (random port) serves the page and a JSON API
  (`/api/state`, `/api/dest`, `/api/pick`, `/api/plan`, `/api/import`, `/api/verify`,
  `/api/eject`, `/api/trash`, `/api/reset`).
  - Every request needs a secret token created at launch, and a `127.0.0.1` Host header, so other
    web pages and other machines can't drive it.
  - Long jobs run in a background thread. The engine reports progress to the page through
    `PROGRESS_HOOK`.
- **Window.** On macOS and Windows the page opens in a native window
  ([pywebview](https://pywebview.flowrl.com/), using the system web view: WebKit on Mac, Edge
  WebView2 on Windows). On Linux, or if that window can't start, it opens in the default browser
  and quits about 45 seconds after the page is closed.
- **Folder picker.** A native dialog everywhere: pywebview's in the window, otherwise AppleScript,
  PowerShell, `zenity` or `kdialog`. You can also paste a path.
- **Engine loading.** The app loads `sony-import.py` at start-up. Because of that, the app imports
  the engine's standard-library modules itself, so PyInstaller packs them into the built app.
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
  - Turn it off with `SONY_IMPORT_NO_UPDATE_CHECK=1`.
- **Saved settings.** The backup folder is remembered in `~/.sony-import.json`.

### Engine commands (internal)

The engine also has commands with JSON output. They're used by the tests and by scripts (such as
a Claude skill that runs backups), and aren't part of the user-facing app:

```bash
python3 sony-import.py detect --dest "$DEST" --json           # cards, backup drive
python3 sony-import.py plan   --dest "$DEST" --json           # what would be copied
python3 sony-import.py import --dest "$DEST" --report r.json  # copy, write a JSON report
python3 sony-import.py verify --dest "$DEST" --json           # byte-for-byte check
python3 sony-import.py eject  [--card PATH]                   # safely eject the card(s)
python3 sony-import.py check-update --json                    # is a newer release out?
python3 sony-import.py trash-jpgs --report r.json             # move extra JPGs to the Trash
```

- **Cards:** `--card PATH` (repeatable) picks specific cards. Otherwise every connected Sony card
  is used.
- **Backup folder:** `--dest` can come from the `SONY_IMPORT_DEST` environment variable instead.
- **Exit codes:**

  | Code | Meaning |
  |---|---|
  | `0` | OK |
  | `1` | Some files failed (for `verify`: not safe to format) |
  | `2` | Bad arguments, or no card |
  | `3` | Not enough space on the backup drive (nothing copied) |

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
  - the update check reports a newer release, ignores an older one, and stays quiet when offline
- **[`tests/app_test.py`](tests/app_test.py)** tests the app the way its page uses it:
  - choose a folder, check what's new, back up, verify, try to eject, then check again
  - requests with no token, a wrong token, or a foreign Host header are refused

```bash
python3 tests/smoke_test.py python3 sony-import.py      # the engine
python3 tests/app_test.py python3 sony-import-app.py    # the app, from source
python3 tests/app_test.py "dist/Sony Import.app/Contents/MacOS/Sony Import"   # a built Mac app
```

Test hooks:

| Variable | What it does |
|---|---|
| `SONY_IMPORT_TEST_CARDS` | Treats these folders as plugged-in cards |
| `SONY_IMPORT_TEST_FREE_BYTES` | Fakes the free space on the backup drive |
| `SONY_IMPORT_UPDATE_URL` | Uses this URL for the update check |
| `SONY_IMPORT_URL_FILE` | Writes the `--serve` URL to a file, for windowed builds without a console |

## The one-line installers

Files downloaded by `curl` or `Invoke-WebRequest` don't get the "downloaded from the internet"
mark. That's why the installed app opens without the Gatekeeper or SmartScreen warnings that
browser downloads hit. The real fix would be paid code signing; this avoids the warnings without
it.

### macOS and Linux: [`install.sh`](install.sh)

It downloads the latest release with `curl`:
- **macOS:** unpacks `Sony Import.app` with `ditto`, keeping its signature. It installs into
  `/Applications`, or into `~/Applications` if that isn't writable, replacing an older version. It
  refuses while the app is open.
- **Linux:** installs `~/.local/bin/sony-import` (it opens in the browser) and an app-menu entry.

| Variable | Default |
|---|---|
| `SONY_IMPORT_RELEASES` | `https://github.com/imsoumya18/sony-import/releases/latest/download` |
| `SONY_IMPORT_RAW` | `https://raw.githubusercontent.com/imsoumya18/sony-import/main` (Linux icon) |
| `SONY_IMPORT_APPS_DIR` | `/Applications` (macOS) |
| `SONY_IMPORT_BIN_DIR` | `~/.local/bin` (Linux) |
| `SONY_IMPORT_NO_REVEAL` | If unset, the app is shown in Finder afterwards |

### Windows: [`install.ps1`](install.ps1)

It runs as `irm …/install.ps1 | iex`, in Windows PowerShell 5.1 or later:
- It downloads `Sony Import.exe` into `%LOCALAPPDATA%\Programs\Sony Import`, which needs no admin
  rights, and adds a **Sony Import** Start-menu shortcut.
- `Unblock-File` makes sure the app carries no "from the internet" mark.
- It runs inside `& { … }` and never calls `exit`, so a failure can't close the user's PowerShell
  window.

Overrides: `SONY_IMPORT_RELEASES`, `SONY_IMPORT_INSTALL_DIR` and `SONY_IMPORT_START_MENU`.

The icons are [`docs/icon.png`](docs/icon.png) (1024 px), [`docs/AppIcon.icns`](docs/AppIcon.icns)
and [`docs/icon.ico`](docs/icon.ico), drawn in the app's teal and orange.

## Building and releasing

On every push, [GitHub Actions](.github/workflows/build.yml) runs these jobs:

| Job | What it does |
|---|---|
| `engine` | Engine tests from source, on Windows, macOS and Linux |
| `app` | Builds the app with PyInstaller for Windows, macOS (Apple Silicon and Intel) and Linux, and runs the app test against each build |
| `installer`, `installer-windows` | Install the app built in the same run with the one-line installers, then run the app test against the installed copy |
| `release` | Only for version tags, and only once all the others pass |

To publish a new version:
1. Add a `## [X.Y.Z] - date` section to [CHANGELOG.md](CHANGELOG.md), written for users. Usually
   you just rename `## [Unreleased]`.
2. Bump `__version__` in `sony-import.py`. The app shows it, and the update notice uses it.
3. Commit, then tag and push:

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```

The release notes are that CHANGELOG section plus the install lines
([`.github/scripts/release-notes.sh`](.github/scripts/release-notes.sh)). If the section is
missing, the job falls back to GitHub's automatic notes and shows a warning. Badges can lag a few
minutes after a release, because the badge service and GitHub cache the image.
