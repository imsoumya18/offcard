# Developing Sony Import

[![Build](https://img.shields.io/github/actions/workflow/status/imsoumya18/sony-import/build.yml?branch=main&label=build)](https://github.com/imsoumya18/sony-import/actions/workflows/build.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-008787)](https://www.python.org/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-008787)](sony-import.py)

The whole tool is one Python file, [`sony-import.py`](sony-import.py). It uses only the standard
library and runs on Python 3.8+. User-facing docs are in the [README](README.md).

## Run from source

```bash
python3 sony-import.py                            # interactive: asks for the backup folder
python3 sony-import.py --dest "/path/to/backup"   # interactive, folder given up front
python3 sony-import.py --version
```

## Scripting

Non-interactive subcommands:

```bash
python3 sony-import.py detect --dest "$DEST"                 # find cards, check the backup drive
python3 sony-import.py plan   --dest "$DEST"                 # dry run: what would be copied
python3 sony-import.py import --dest "$DEST" --report r.json # copy, write a JSON report
python3 sony-import.py verify --dest "$DEST"                 # byte-for-byte check: safe to format?
python3 sony-import.py check-update [--json]                 # is a newer release out?
python3 sony-import.py trash-jpgs --report r.json            # move JPGs that have an ARW twin to the Trash
```

- **Backup folder:** the subcommands need `--dest`, or the `SONY_IMPORT_DEST` environment variable.
  Interactive mode always asks unless `--dest` is given.
- **Choosing cards:** `--card PATH` (repeatable) picks specific cards. Otherwise every connected
  Sony card is used.
- **JSON output:** `--json` gives machine-readable output for `detect` and `plan`. `plan` includes
  `needed_bytes`, `free_bytes` and `enough_space`.
- **Exit codes:** `0` OK, `1` some files failed (for `verify`: not safe to format), `2` bad
  arguments or no card, `3` not enough space on the backup drive (nothing copied).
- **Progress for scripts:** when output isn't a terminal, there's no colour and no animated bars.
  Copy progress is printed as `PROGRESS NN% ...` lines instead.

## How it works

- **Card detection.** A drive counts as a Sony card when it has a `DCIM` folder named like
  `100MSDCF` or `10161017` and a `PRIVATE/M4ROOT` folder. Drives are looked for in these places:
  - macOS: `/Volumes`
  - Linux: `/media`, `/run/media`, `/mnt`
  - Windows: drive letters
- **What's copied.**
  - Photos: `.ARW`, `.JPG`, `.HIF` from every `DCIM` subfolder.
  - Videos: `PRIVATE/M4ROOT/CLIP/*.MP4` plus their `M01.XML` sidecar files.
  - Ignored: proxies, thumbnails and AVCHD.
- **Dates.**
  - Photos: EXIF `DateTimeOriginal`, read by a small built-in parser (no exiftool needed).
  - Videos: the `CreationDate` in Sony's XML file.
- **Duplicate check.** There is no database. The backup folder is scanned each run, and every
  card file is matched on its own by size and a hash of three 64 KB samples (start, middle, end).
  Names and dates aren't used, so renamed files still match. Size alone isn't enough, because
  Sony's compressed RAW files are all the same size.
- **Pairs.** A video (`.MP4` + `.XML`) or a RAW + JPG photo that is only half backed up gets the
  missing half copied next to the half that's there, under the same number. The exception: a JPG
  whose RAW is backed up is treated as removed on purpose (the Trash option), so it isn't copied back.
- **Numbering.** New files continue from the highest `DSC#####` / `C#####` already in the backup.
  Orphan `.XML` files count too, so numbers never collide.
- **Free space.** Before copying, the needed bytes (plus a 50 MB margin) are compared with the free
  space on the backup drive. The tests fake a full drive with `SONY_IMPORT_TEST_FREE_BYTES`.
- **Verify ("safe to format?").** Every card file is located in the backup by size + fingerprint,
  then compared in full, byte for byte. A file can come out *verified*, *missing*, or *different*
  (a damaged copy). A JPG whose RAW is backed up but which is itself missing counts as trashed on
  purpose, which is not a failure. The card is safe only if nothing is missing or different.
- **Copying.** Each file is written as `*.partial`, its size is checked, and then it's renamed into
  place. The original file timestamp is kept.
- **Trash.** Uses Finder on macOS, the Recycle Bin via PowerShell on Windows (refused on removable
  drives, which have no Recycle Bin), and `gio trash` / `trash-cli` on Linux.
- **Update notice.** Interactive mode only: at startup, a background thread asks the GitHub API
  for the latest release (3-second timeout). It falls back to `curl` if Python can't verify HTTPS,
  and says nothing when offline. If the release is newer than `__version__`, a note with the
  update command is shown at the end. Turn it off with `SONY_IMPORT_NO_UPDATE_CHECK=1`. The URL
  can be overridden with `SONY_IMPORT_UPDATE_URL`, which the tests use. Subcommands never touch
  the network, except `check-update`.
- **Saved settings.** The last chosen backup folder is stored in `~/.sony-import.json`. It's only
  offered as the Enter shortcut, never used without asking.

## Terminal colours

Each colour has one job, and each one is readable on both dark and light terminals (contrast of
about 3.5:1 or better on black and on white). Note that macOS Terminal's default theme is white.

| Role | Colour | Used for |
|---|---|---|
| Structure | teal `#008787` (256-colour 30) | banner, step headings, both progress bars, prompt keys |
| Needs attention | orange `#d75f00` (166) | new files, warnings, missing drives, RAW + JPG list |
| Success | green `#008700` (28) | ✓, already backed up, copied, all done |
| Error | red `#d75f5f` (167) | failures only |
| Content | bold default text | paths and day folders |
| Secondary | dim | labels, hints, sizes |

Colour turns off in these cases:
- the output isn't a terminal
- `NO_COLOR` is set
- `TERM=dumb`

Consoles that can't show `█ ✓ ⚠ →` get plain ASCII instead.

## Tests

[`tests/smoke_test.py`](tests/smoke_test.py) builds a fake Sony card (tiny JPG/ARW files with
real EXIF dates, a burst pair and a video), imports it, and checks the exact folder tree. It then
checks that:
- a second run copies nothing
- each half of a video or RAW + JPG pair deleted from the backup is put back under the same name
- a deleted single photo comes back once
- renamed files are still recognised
- a JPG trashed on purpose isn't brought back
- `verify` passes after an import, and catches a backup copy with one byte changed (in a spot the
  quick fingerprint doesn't sample) and a missing backup file
- a full backup drive stops the import before anything is copied (exit code 3)
- `check-update` reports a newer release, ignores an older one, and stays quiet when offline

```bash
python3 tests/smoke_test.py python3 sony-import.py   # test the script
python3 tests/smoke_test.py ./dist/sony-import       # test a built app
```

## The one-line installers

### Windows: `install.ps1`

The README's PowerShell line runs `irm …/install.ps1 | iex` (Windows PowerShell 5.1 or later).
It downloads `sony-import-windows.exe` into `%LOCALAPPDATA%\Programs\Sony Import`, which needs no
admin rights, and adds a **Sony Import** Start-menu shortcut. Files downloaded by
`Invoke-WebRequest` don't get the Mark-of-the-Web, so SmartScreen doesn't warn; `Unblock-File`
makes sure of it. The script runs inside `& { … }` and never calls `exit`, so a failure can't close
the user's PowerShell window. The Windows build embeds [`docs/icon.ico`](docs/icon.ico).

Overrides, used by CI: `SONY_IMPORT_RELEASES`, `SONY_IMPORT_INSTALL_DIR`, `SONY_IMPORT_START_MENU`.

### macOS and Linux: `install.sh`

[`install.sh`](install.sh) is what the README's Terminal line runs (macOS and Linux). It downloads
the latest release with `curl` and installs it:
- **macOS:** a small `Sony Import.app` in `/Applications`, or `~/Applications` if that isn't
  writable. Its launcher opens the tool in a Terminal window, and it uses the icon in
  [`docs/AppIcon.icns`](docs/AppIcon.icns).
- **Linux:** `~/.local/bin/sony-import` plus an app-menu entry.

Files downloaded by `curl` don't get macOS's quarantine mark, so the app opens without the
Gatekeeper block that browser downloads hit. The real fix would be signing and notarizing with a
paid Apple Developer ID. This avoids the block without that.

Environment overrides (used by CI to test it):

| Variable | Default |
|---|---|
| `SONY_IMPORT_RELEASES` | `https://github.com/imsoumya18/sony-import/releases/latest/download` |
| `SONY_IMPORT_RAW` | `https://raw.githubusercontent.com/imsoumya18/sony-import/main` (icons) |
| `SONY_IMPORT_APPS_DIR` | `/Applications` (macOS) |
| `SONY_IMPORT_BIN_DIR` | `~/.local/bin` (Linux) |
| `SONY_IMPORT_NO_REVEAL` | unset: when unset, it shows the app in Finder afterwards |

The icon source is [`docs/icon.png`](docs/icon.png) (1024 px). It's drawn in the app's teal and orange.

## Building and releasing

[GitHub Actions](.github/workflows/build.yml) builds standalone apps with PyInstaller on Windows,
macOS (Apple Silicon and Intel) and Linux, and runs the smoke test against each one. It also runs
the one-line installers on Windows (PowerShell 5.1), Linux and both Macs. This happens on every push. Pushing a version tag also publishes the apps as a GitHub Release:

```bash
git tag v1.2.0 && git push origin v1.2.0
```

Bump `__version__` in `sony-import.py` first; the app shows it in its banner.
