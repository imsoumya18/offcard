# sony_import

Back up photos and videos from Sony camera memory cards to an external drive, sorted into
**Year → Month → Day** folders. Anything already in the backup is skipped automatically.

It is one Python file with no dependencies, made for macOS.

```
Sony Backup/
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

## Features

- **Never touches the card.** Files are only read from it. Nothing is renamed, moved or deleted.
- **Finds Sony cards by folder layout**, whatever the card's name. You can import from several cards at once.
- **Sorts by the date the photo or video was taken.**
  - Photos use the EXIF `DateTimeOriginal`.
  - Videos use the `CreationDate` from Sony's XML sidecar file.
- **Only creates folders that have something in them.** A day, month or year with no shots gets no folder.
  - Photos go straight into the day folder.
  - Videos (MP4 + XML) go into a `Videos` subfolder.
- **Skips files already in the backup without keeping a database.** Every run scans the backup
  folder and matches files by size, capture time and a hash of three small content samples.
  - Files you renamed in the backup are still recognised.
  - Pointing it at a different backup folder just works.
- **Renumbers everything in shooting order.** Sony's own counters reset, and different cards
  reuse the same names. Each imported file gets a new running number, continuing from the highest
  number already in the backup:
  - Photos: `DSC00001`
  - Videos: `C00001`
  - A RAW+JPG pair shares one number.
- **Lists RAW+JPG pairs after an import**, and can move the duplicate JPGs to the Trash.
  Trashed JPGs are not re-imported next time.
- **Shows a progress bar** while copying. Each file is copied as `.partial`, its size is checked, and only then is it renamed into place.
  An interrupted import leaves no half-written files under real names.

## Requirements

- macOS (uses `/Volumes`, `sips` and Finder's Trash)
- Python 3.8+ (the one that comes with Xcode Command Line Tools is fine)
- A Sony camera. Tested with the a6600 (ILCE-6600). Other Alpha and ZV models use the same card
  layout, so they should work too.

## Install

```bash
git clone https://github.com/imsoumya18/sony_import.git
cd sony_import
```

Optionally, set your backup folder once (for example in `~/.zshrc`) so you don't have to pass `--dest` every time:

```bash
export SONY_IMPORT_DEST="/Volumes/MySSD/Photos/Sony Backup"
```

## Usage

### Interactive (recommended)

Plug in the card and the backup drive, then run:

```bash
python3 sony_import.py --dest "/Volumes/MySSD/Photos/Sony Backup"
```

It walks you through each step and waits for a yes before continuing:

1. **Checks the drives.** If the card or the backup drive is missing, it says so and stops.
2. **Shows the source and destination.** You can confirm, cancel, or type a different backup folder.
3. **Reports what's new on each card.** Counts, size, and the date range of the new shots.
4. **Copies** with a progress bar.
5. **Shows a final report** per day folder and lists any RAW+JPG pairs. It offers to move those JPGs to the Trash.

### Step by step (scripting)

```bash
python3 sony_import.py detect --dest "$DEST"                 # find cards, check backup drive
python3 sony_import.py plan   --dest "$DEST"                 # dry run: what would be copied
python3 sony_import.py import --dest "$DEST" --report r.json # copy, write a JSON report
python3 sony_import.py trash-jpgs --report r.json            # trash JPGs that have an ARW twin
```

- **Choosing cards:** `plan` and `import` use every connected Sony card. Use `--card /Volumes/NAME`
  (repeatable) to pick specific ones.
- **JSON output:** add `--json` to `detect` or `plan` for machine-readable output.
- **Progress output:** when the output isn't a terminal, progress is printed as `PROGRESS NN%` lines.

## How a card is recognised

A mounted volume counts as a Sony card when it has both:

- `DCIM/` with at least one Sony-style folder: `100MSDCF` (standard) or `10161017` (date
  format: folder number, last digit of the year, month, day)
- `PRIVATE/M4ROOT/` (where Sony stores video clips)

What gets copied:

- **Photos:** `.ARW`, `.JPG`, `.HIF` from every `DCIM` subfolder
- **Videos:** `PRIVATE/M4ROOT/CLIP/*.MP4` with their `M01.XML` sidecar files

Proxy clips, thumbnails and AVCHD files are ignored.

## Things to know

- **Dates are camera local time.** If the camera clock is wrong, the folders will be too.
- **Numbering can be out of date order.** Existing backup files are never renamed. If you import
  a card with older shots after a newer one, the older shots get higher numbers. They still land
  in the right date folders.
- **A full card takes a while to scan.** Every file is read to get its date, which takes about
  40 seconds for ~350 files over USB. Copying speed depends on your card reader and drive.

## License

MIT, see [LICENSE](LICENSE).
