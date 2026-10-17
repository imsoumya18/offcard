# Sony Import

Back up the photos and videos from your Sony camera's memory card to a computer or external drive,
neatly sorted into **Year → Month → Day** folders. Run it again any time: it only copies what's new.

**Works on Windows, macOS and Linux. Nothing to install: download one file and double-click it.**

<p align="center"><img src="docs/screenshot.png" alt="Sony Import checking a memory card before copying" width="720"></p>

The result on your drive looks like this:

```
Camera Backup/          ← any folder you choose
├── 2026/
│   ├── 9. September/
│   │   ├── 05Sep26/
│   │   │   ├── DSC00001.ARW
│   │   │   ├── DSC00001.JPG
│   │   │   ├── DSC00002.ARW
│   │   │   └── Videos/
│   │   │       ├── C00001.MP4
│   │   │       └── C00001M01.XML
│   │   └── 14Sep26/
│   └── 10. October/
└── 2027/
```

## Download

Pick the file for your computer:

| Your computer | Download |
|---|---|
| Windows | [sony-import-windows.exe](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-windows.exe) |
| Mac with Apple chip (M1, M2, M3…) | [sony-import-macos-apple-silicon.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-macos-apple-silicon.zip) |
| Mac with Intel chip | [sony-import-macos-intel.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-macos-intel.zip) |
| Linux (64-bit PC) | [sony-import-linux.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-linux.zip) |

Not sure which Mac you have? Click the Apple menu  → **About This Mac** and look at "Chip" or "Processor".

### First time opening it

The app isn't signed with a paid Apple or Microsoft certificate, so your computer will warn you the first time. You only need to do this once.

- **Windows:** double-click `sony-import-windows.exe`. If you see "Windows protected your PC",
  click **More info** → **Run anyway**.
- **Mac:** double-click the zip to unzip it, then double-click `sony-import`.
  - If macOS says it can't verify the app, click **Done**.
  - Then open **System Settings → Privacy & Security**, scroll down, click **Open Anyway** next to
    "sony-import", and confirm.
- **Linux:** unzip it, open a terminal in that folder and run `./sony-import`.

## How to use it

1. Put the camera's memory card in your computer, and plug in the drive you back up to (if you use one).
2. Double-click **sony-import**. A window opens and walks you through five steps:
   1. **Backup folder:** choose where your photos should go. **Drag the folder into the window**
      (or type its path) and press Enter. It can be any folder on any drive. Next time it offers
      the same folder again, and you just press Enter to reuse it.
   2. **Connect:** checks that both the card and the backup drive are plugged in. If one is
      missing it tells you, and waits while you plug it in.
   3. **Confirm:** shows where it will copy from and to, so you can change the folder if needed.
   4. **Check what's new:** how many photos and videos aren't backed up yet, how big they are,
      and which dates they're from.
   5. **Copy:** type `y` and watch the progress bar go to 100%. If you shot RAW + JPG, it lists
      those photos and offers to move the extra JPG copies to the Trash / Recycle Bin. You can
      always get them back from there.
3. When it says **All done**, you can safely eject the card.

## What it does (and doesn't)

- **Your memory card is never changed.** Files are only read from it, never deleted, moved or renamed.
- **Sorted by the date you took the photo**, not the date you copied it. A day, month or year with
  no photos gets no folder. Videos go into a `Videos` folder inside their day.
- **No duplicates.** Each time, it checks what's already in your backup folder and skips it, even if
  you renamed files there or are using several memory cards.
- **Fills gaps.** It checks every file on its own. If a video's `.XML` file is missing from the
  backup, it puts back just the `.XML` next to its video, with the same number. The same goes for
  a video whose `.MP4` is missing, or the RAW half of a RAW + JPG photo.
- **One clean numbering.** Sony restarts its file numbers on every card, so the same name can turn
  up twice. Imported files are renamed in shooting order: `DSC00001`, `DSC00002`… for photos and
  `C00001`… for videos. Numbering continues from the highest number already in the backup.
- **Safe if interrupted.** Unplugging the drive or closing the window never leaves half-copied
  files behind. Just run it again to finish.

### Which cameras?

It's made for Sony cameras that store photos in `DCIM` and videos in `PRIVATE/M4ROOT` on the card.
That covers Alpha models (a6000 series, a7 series and others) and ZV models. It's tested with the a6600.

It copies RAW (`.ARW`), JPG and HEIF (`.HIF`) photos, and MP4 videos with their `.XML` files.

### Good to know

- **Dates come from the camera's clock.** If the clock is wrong, the folders will be too.
- **Numbering can be out of date order.** Files already in your backup are never renamed. If you
  import an older card after a newer one, the older photos get higher numbers. They still go into
  the right date folders.
- **Checking a full card takes about a minute** before copying starts.

## For developers

The whole tool is one Python file, [`sony-import.py`](sony-import.py), using only the standard
library (Python 3.8+). You can run it directly instead of downloading the app:

```bash
python3 sony-import.py                       # interactive: asks for the backup folder
python3 sony-import.py --dest "/path/to/backup"   # interactive, folder given up front
```

There are also non-interactive subcommands for scripting:

```bash
python3 sony-import.py detect --dest "$DEST"                 # find cards, check the backup drive
python3 sony-import.py plan   --dest "$DEST"                 # dry run: what would be copied
python3 sony-import.py import --dest "$DEST" --report r.json # copy, write a JSON report
python3 sony-import.py trash-jpgs --report r.json            # move JPGs that have an ARW twin to the Trash
```

- **Backup folder:** the subcommands need `--dest`, or the `SONY_IMPORT_DEST` environment variable.
  Interactive mode always asks unless `--dest` is given.
- **Choosing cards:** `--card PATH` (repeatable) picks specific cards. Otherwise every connected Sony card is used.
- **JSON output:** `--json` gives machine-readable output for `detect` and `plan`.

### How it works

- **Card detection.** A drive counts as a Sony card when it has a `DCIM` folder named like
  `100MSDCF` or `10161017` and a `PRIVATE/M4ROOT` folder. Drives are looked for in these places:
  - macOS: `/Volumes`
  - Linux: `/media`, `/run/media`, `/mnt`
  - Windows: drive letters
- **Dates.**
  - Photos: EXIF `DateTimeOriginal`, read by a small built-in parser, so no exiftool is needed.
  - Videos: the `CreationDate` in Sony's XML file.
- **Duplicate check.** There is no database. The backup folder is scanned each run, and every
  card file is matched on its own by size and a hash of three 64 KB samples (start, middle, end).
  Names and dates aren't used, so renamed files still match. Size alone isn't enough, because
  Sony's compressed RAW files are all the same size.
- **Pairs.** A video (`.MP4` + `.XML`) or a RAW + JPG photo that is only half backed up gets the
  missing half copied next to the half that's there, under the same number. The exception: a JPG
  whose RAW is backed up is treated as removed on purpose (the Trash option), so it isn't copied back.
- **Copying.** Each file is written as `*.partial`, its size is checked, and then it's renamed into
  place. The original file timestamp is kept.
- **Trash.** Uses Finder on macOS, the Recycle Bin via PowerShell on Windows (refused on removable
  drives, which have no Recycle Bin), and `gio trash` / `trash-cli` on Linux.
- **Saved settings.** The last chosen backup folder is stored in `~/.sony-import.json`. It is only
  offered as the Enter shortcut, never used without asking.

### Building and releasing

[GitHub Actions](.github/workflows/build.yml) builds the standalone apps with PyInstaller on
Windows, macOS (Apple Silicon and Intel) and Linux. It also runs
[`tests/smoke_test.py`](tests/smoke_test.py) against each one. That test creates a fake Sony card,
imports it, and checks the resulting folders. To publish a new version:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

## License

MIT, see [LICENSE](LICENSE).
