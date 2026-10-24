# What's new in Sony Import

To update, run the install line from the [README](README.md#install) again. The app tells you
when a new version is out.

## [2.0.0] - 2026-10-24

- **Sony Import is now a desktop app.** One window instead of a terminal: your card and backup
  folder, what's new and what's already backed up, and one **Back up** button with a progress bar.
  Then there are buttons to **check it's safe to format**, **eject the card**, and move extra JPGs
  to the Trash. It follows your computer's light or dark mode.
- **The terminal version is gone.** To switch, run the install line from the README once more. It
  replaces the old version with the app, under the same name.
- **Eject the card** with one click when you're done. It only ever ejects; it never formats or
  deletes anything.
- On Linux, the app opens in your web browser.

## [1.3.1] - 2026-10-22

- **Realistic time estimate** for the "safe to format" check. It used to promise about 5 minutes
  for a 22 GB card that really took about 10.
- **Shorter question** for that check, so it fits on one line.
- Finished progress bars no longer show "0s left".

## [1.3.0] - 2026-10-22

- **"Safe to format?" check.** Optionally checks every file on the card against your backup,
  byte by byte, and tells you clearly when it's safe to format the card in your camera, or
  exactly which files aren't backed up yet.
- **Free-space check.** Stops before copying if your backup drive doesn't have room, instead of
  failing halfway.
- **Update notice.** Tells you when a newer version is available, with the line to install it.
- **One-line install on Windows.** Paste one line into PowerShell. There's no SmartScreen
  warning, and Sony Import appears in the Start menu with its own icon.
- **The Mac window now closes** when you press Enter at the end.

## [1.2.0] - 2026-10-17

- **You choose the backup folder.** Drag it into the window or type it. Nothing is assumed, and
  the folder you used last time is offered as a shortcut.
- **Fills gaps.** If a video's `.XML` or `.MP4`, or the RAW of a RAW + JPG photo, is missing from
  the backup, just that file is put back, next to its partner, with the same number.
- **New colours** that are easy to read on both dark and light terminals.
- **One-line install on Mac and Linux**, with no Mac security warning. Sony Import gets its own
  app icon.

## [1.1.0] - 2026-10-17

- **Colourful, guided screens** with numbered steps.
- **Progress bar while checking** what's already backed up, not only while copying.

## [1.0.0] - 2026-10-17

- First release. Backs up photos and videos from Sony camera cards into Year → Month → Day
  folders, skips anything already backed up, and runs on Windows, macOS and Linux with nothing
  to install.
