# Sony Import

[![Download](https://img.shields.io/github/v/release/imsoumya18/sony-import?label=download&color=008787)](https://github.com/imsoumya18/sony-import/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/imsoumya18/sony-import/build.yml?branch=main&label=build)](https://github.com/imsoumya18/sony-import/actions/workflows/build.yml)
[![Downloads](https://img.shields.io/github/downloads/imsoumya18/sony-import/total)](https://github.com/imsoumya18/sony-import/releases)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-008787)](#download)
[![No install needed](https://img.shields.io/badge/install-not%20needed-008787)](#download)
[![License: MIT](https://img.shields.io/github/license/imsoumya18/sony-import?color=008787)](LICENSE)

Back up the photos and videos from your Sony camera's memory card, neatly sorted into
**Year → Month → Day** folders. Run it again any time: it only copies what's new.

<p align="center"><img src="docs/screenshot.png" alt="Sony Import checking a memory card before copying" width="720"></p>

## Download

| Your computer | Download |
|---|---|
| Windows | [sony-import-windows.exe](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-windows.exe) |
| Mac with Apple chip (M1, M2, M3…) | [sony-import-macos-apple-silicon.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-macos-apple-silicon.zip) |
| Mac with Intel chip | [sony-import-macos-intel.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-macos-intel.zip) |
| Linux (64-bit) | [sony-import-linux.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-linux.zip) |

Not sure which Mac you have? Apple menu  → **About This Mac** → look at "Chip".

<details>
<summary><b>Your computer warns you the first time you open it?</b> (click to see what to do)</summary>

The app is free and not signed with a paid Apple or Microsoft certificate, so the first time:

- **Windows:** on "Windows protected your PC", click **More info** → **Run anyway**.
- **Mac:** unzip it and double-click `sony-import`. When macOS says it can't verify the app:
  1. Click **Done**.
  2. Go to **System Settings → Privacy & Security**.
  3. Scroll down and click **Open Anyway**.
- **Linux:** unzip it, open a terminal in that folder and run `./sony-import`.

You only need to do this once.
</details>

## How to use it

1. Put the memory card in your computer, and plug in the drive you back up to.
2. Double-click **sony-import**.
3. **Choose your backup folder:** drag the folder into the window and press Enter. It can be any
   folder on any drive. Next time, just press Enter to reuse it.
4. Check what it found, type `y` to start copying, and wait for **All done**.

That's it. You can safely eject the card.

Your backup folder will look like this:

```
Camera Backup/                ← the folder you chose
└── 2026/
    └── 9. September/
        └── 05Sep26/
            ├── DSC00001.ARW
            ├── DSC00001.JPG
            └── Videos/
                ├── C00001.MP4
                └── C00001M01.XML
```

## What it does

- **Never changes your memory card.** It only reads from it.
- **Sorts by the date you took each photo.** There are no empty folders, and videos go in a
  `Videos` folder inside their day.
- **Never copies the same photo twice**, even if you renamed files in the backup or use several cards.
- **Fills gaps.** If a video or RAW + JPG photo is only half backed up, it copies just the missing half.
- **Gives every file one clean number** in shooting order (`DSC00001`…, `C00001`…), so names
  never clash.
- **Shot in RAW + JPG?** It offers to move the extra JPGs to the Trash. You can restore them from there.
- **Safe to interrupt.** If you close the window midway, just run it again to finish.

## Good to know

- **Cameras:** works with Sony Alpha (a6000 series, a7 series…) and ZV cameras. Tested on the a6600.
- **Folder dates use the camera's clock**, so make sure it's set correctly.
- **Checking a full card takes about a minute** before copying starts.

---

Developers: see **[DEVELOPMENT.md](DEVELOPMENT.md)** for running from source, scripting, how it
works, and releasing. Licensed under [MIT](LICENSE).
