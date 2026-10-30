# What's new in offcard

To update, run the install line from the [README](README.md#install) again. The app tells you
when a new version is out.

offcard was called **ShotLoft** up to v0.9.1, and **Sony Import** up to v0.4.0.

## [0.12.1] - 2026-10-30

- A shorter README: what offcard does, how to install it, and how to use it.
- The launch video now shows tagging a day and the new Back Up button.

## [0.12.0] - 2026-10-30

- **Tag a day.** Next to the day's folder, **+ Add tag** names it for what happened: Ooty,
  Birthday, Reunion. The folder becomes `24Oct26 - Birthday` (without a tag, still `24Oct26`).
  A day already on the drive is renamed, with everything in it, and later backups of that day go
  into the same tagged folder. Back from a trip with several days on the card? **Add tags ›** lists
  each day, and each gets its own tag; your recent tags are a click away, so tagging three days
  "Goa" is three clicks.
- **Back up only some files.** Back Up still backs up everything in one click. Its new **⌄** has
  Photos Only, Videos Only and **Choose Files…**: tick whole days, or open a day and pick its photos
  and videos from small previews (RAW + JPG pairs and videos are marked). Files you leave out stay on
  the card and show as new next time; the ones you back up are numbered without gaps.
- On a Mac. On Windows and Linux, everything on the card is backed up into untagged day folders,
  and days you've tagged on a Mac keep their folders.

## [0.11.1] - 2026-10-30

- **The panel's footer reads as preferences**, not features: Open at Login and Quit sit on a quiet
  tray in smaller type, Quit highlights under the pointer (and ⌘Q works), and the version is shown
  there too.

## [0.11.0] - 2026-10-30

- **HDR Merge lives in the popup.** On a Mac, click HDR Merge and the panel slides to its page; ‹
  slides back. No more separate window. The sets are listed by day with a bracket glyph instead of
  photos, the new ones are ticked, and the button says what it does: **Merge 3 Sets**, then
  **Show in Finder**. Each set shows its own progress while merging, and the popup stays the same
  size throughout. The folder, selections and the 16-bit TIFF option are in the page's header.

## [0.10.0] - 2026-10-30

- **ShotLoft is now offcard.** A new name and a new icon: three chevrons on graphite, the same
  mark as in the menu bar. Running the install line replaces ShotLoft with offcard and keeps your
  backup folder and recent folders. Old install lines and links still work.
- **A new panel.** Your card on the left, the drive on the right, three chevrons between them.
  It's centred, quieter and the same size in every state, so nothing jumps. Ink (white in dark
  mode, black in light) marks what matters now: a card with new files, the check when it's done,
  and the one button, which always says exactly what it does.
- **Copying you can watch.** The card's icon turns into a ring that fills with liquid and shows
  the percentage, the chevrons run toward the drive, and it says about how long is left. When it's
  done, the next step is the button: Check Before Formatting, then Eject.
- **On a Mac, macOS asks once more for access to your memory card**, because the app has a new
  identity. Open at Login is set up again on the first run.

## [0.9.1] - 2026-10-30

- **A launch video** at the top of the README: card in, the folders it goes into, Back Up, safe to
  format, and HDR Merge, in 23 seconds.
- **The README's steps match the new panel**: Change under Back Up To, the Back Up button that
  says how much is new, and Check Before Formatting.

## [0.9.0] - 2026-10-30

- **See the folders before you back up.** On a Mac, once a card is checked, the panel shows the
  folder tree the backup will create under the folder you chose: which folders are already there,
  which are new, and how many files go into each.
- **A redesigned panel, built like the Mac's own menus.** Memory Card, Back Up To and Tools, each
  under a small heading, in a quiet graphite. The button says exactly what it does ("Back Up 6
  Photos"), copying shows the percentage in a ring that fills with liquid as it goes, with "About
  2 minutes left", and Open at Login and Quit sit at the bottom. The panel shows no photos from
  the card.
- **Portrait photos stand upright** in HDR Merge.

## [0.8.0] - 2026-10-30

- **Choose where each backup goes.** Under the card, "To …" lists the backup folders you've used,
  and Choose Folder… for another one, so every backup can go somewhere different.
- **A smaller, quieter panel.** The backup button sits next to the card, and everything else is
  under ⋯.
- **No notification requests.** macOS only allows notifications from apps signed by a registered
  Apple developer, so the menu bar icon's dot shows when a card has new photos instead.

## [0.7.0] - 2026-10-29

- **A native Mac app.** The menu bar panel and the HDR Merge window are rebuilt in SwiftUI, in the
  manner of the Mac's own menus and Photos: the newest photo on your card at the top (with the
  copy progress around it), plain rows on the system's Liquid Glass, and HDR Merge as a photo grid
  grouped by day. The panel also tells you how many bracketed sets are waiting to be merged.

## [0.6.0] - 2026-10-29

- **ShotLoft moves to the menu bar on the Mac.** Click the aperture icon for a panel on Liquid
  Glass with your card, your backup drive and the tools; there's no window or Dock icon to manage.
  Put in a card and ShotLoft checks it by itself, tells you what's new, and puts a dot on the icon;
  while it copies, the icon shows the progress. HDR Merge opens in its own window. ShotLoft now
  opens at login, which you can switch off in the panel.
- **Photos get their own folder.** Each day folder now has `Photos`, `Videos` and, for HDR Merge
  results, `HDR`, and only the ones with files in them. Photos you already backed up stay where
  they are and are still recognised, so nothing is copied twice.

## [0.5.0] - 2026-10-24

- **A home for every tool.** ShotLoft now opens on its tools, **Card Backup** and **HDR Merge**,
  so you pick what you want to do. More tools will join them.
- **HDR Merge.** Shot an exposure bracket (BRK C)? Choose a folder, and ShotLoft finds the sets in
  it and all its subfolders by itself, then merges each one into a single, natural-looking photo
  with detail in both the brightest and darkest parts. It lines up handheld shots, leaves out
  anything that moved, and uses the cleanest parts of every shot, so shadows have much less noise.
  The result goes into an `HDR` folder next to the shots, with an optional 16-bit TIFF for editing.
  Your originals are never changed.

## [0.4.2] - 2026-10-24

- **A new app icon:** a camera aperture in ShotLoft's teal and orange.
- **The installer shows its progress straight away.** It used to sit silent on a slow
  connection. Now it counts while connecting to GitHub, then shows a progress bar with how many
  MB are done. If ShotLoft is open, it asks you to quit it before downloading, not after.

## [0.4.1] - 2026-10-24

- **Sony Import is now ShotLoft.** A new name for an app that does more than import: it backs up,
  checks, organises, and will keep growing. To switch, run the install line from the README once.
  It installs ShotLoft and removes the old Sony Import app, and your saved backup folder carries
  over.

## [0.4.0] - 2026-10-24

- **ShotLoft is now a desktop app.** One window instead of a terminal: your card and backup
  folder, what's new and what's already backed up, and one **Back up** button with a progress bar.
  Then there are buttons to **check it's safe to format**, **eject the card**, and move extra JPGs
  to the Trash. It follows your computer's light or dark mode.
- **The terminal version is gone.** To switch, run the install line from the README once more. It
  replaces the old version with the app, under the same name.
- **Eject the card** with one click when you're done. It only ever ejects; it never formats or
  deletes anything.
- On Linux, the app opens in your web browser.

## [0.3.1] - 2026-10-22

- **Realistic time estimate** for the "safe to format" check. It used to promise about 5 minutes
  for a 22 GB card that really took about 10.
- **Shorter question** for that check, so it fits on one line.
- Finished progress bars no longer show "0s left".

## [0.3.0] - 2026-10-22

- **"Safe to format?" check.** Optionally checks every file on the card against your backup,
  byte by byte, and tells you clearly when it's safe to format the card in your camera, or
  exactly which files aren't backed up yet.
- **Free-space check.** Stops before copying if your backup drive doesn't have room, instead of
  failing halfway.
- **Update notice.** Tells you when a newer version is available, with the line to install it.
- **One-line install on Windows.** Paste one line into PowerShell. There's no SmartScreen
  warning, and ShotLoft appears in the Start menu with its own icon.
- **The Mac window now closes** when you press Enter at the end.

## [0.2.0] - 2026-10-17

- **You choose the backup folder.** Drag it into the window or type it. Nothing is assumed, and
  the folder you used last time is offered as a shortcut.
- **Fills gaps.** If a video's `.XML` or `.MP4`, or the RAW of a RAW + JPG photo, is missing from
  the backup, just that file is put back, next to its partner, with the same number.
- **New colours** that are easy to read on both dark and light terminals.
- **One-line install on Mac and Linux**, with no Mac security warning. ShotLoft gets its own
  app icon.

## [0.1.1] - 2026-10-17

- **Colourful, guided screens** with numbered steps.
- **Progress bar while checking** what's already backed up, not only while copying.

## [0.1.0] - 2026-10-17

- First release. Backs up photos and videos from Sony camera cards into Year → Month → Day
  folders, skips anything already backed up, and runs on Windows, macOS and Linux with nothing
  to install.
