# Sony Import

[![Latest version](https://img.shields.io/github/v/release/imsoumya18/sony-import?label=version&color=008787)](https://github.com/imsoumya18/sony-import/releases/latest)
[![Build](https://img.shields.io/github/actions/workflow/status/imsoumya18/sony-import/build.yml?branch=main&label=build)](https://github.com/imsoumya18/sony-import/actions/workflows/build.yml)
[![Downloads](https://img.shields.io/github/downloads/imsoumya18/sony-import/total)](https://github.com/imsoumya18/sony-import/releases)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-008787)](#install)
[![Setup](https://img.shields.io/badge/setup-one%20line-008787)](#install)
[![License: MIT](https://img.shields.io/github/license/imsoumya18/sony-import?color=008787)](LICENSE)

Back up the photos and videos from your Sony camera's memory card, neatly sorted into
**Year → Month → Day** folders. Run it again any time: it only copies what's new.

<p align="center"><img src="docs/screenshot.png" alt="Sony Import confirming that every file on a memory card is backed up and it's safe to format" width="720"></p>

## Install

### Mac and Linux: one line, no security warnings

1. Open **Terminal**: press <kbd>⌘</kbd> <kbd>Space</kbd>, type `Terminal`, press <kbd>Enter</kbd>.
2. Paste this line and press <kbd>Enter</kbd>:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/imsoumya18/sony-import/main/install.sh | bash
   ```

3. **Sony Import** now appears in your Applications folder and Launchpad. Double-click it whenever
   you want to back up a card.

It picks the right version for your computer (Mac with Apple or Intel chip, or Linux) by itself.
To update, run the same line again. On Linux, Sony Import appears in your app menu.

### Windows: one line, no security warnings

1. Open **PowerShell**: click Start, type `PowerShell`, press <kbd>Enter</kbd>.
2. Paste this line and press <kbd>Enter</kbd>:

   ```powershell
   irm https://raw.githubusercontent.com/imsoumya18/sony-import/main/install.ps1 | iex
   ```

3. **Sony Import** is now in your Start menu. Search for it whenever you want to back up a card.

To update, run the same line again. No admin rights needed.

<details>
<summary>Prefer to download the app directly?</summary>

| Your computer | Download |
|---|---|
| Windows | [sony-import-windows.exe](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-windows.exe) |
| Mac with Apple chip (M1, M2, M3…) | [sony-import-macos-apple-silicon.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-macos-apple-silicon.zip) |
| Mac with Intel chip | [sony-import-macos-intel.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-macos-intel.zip) |
| Linux (64-bit) | [sony-import-linux.zip](https://github.com/imsoumya18/sony-import/releases/latest/download/sony-import-linux.zip) |

- **Mac:** unzip it and double-click `sony-import`. Because it was downloaded in a browser,
  macOS blocks it the first time:
  1. Click **Done**.
  2. Go to **System Settings → Privacy & Security**.
  3. Scroll down and click **Open Anyway**.

  The Terminal line above avoids this, which is why it's the recommended way.
- **Windows:** double-click it. On "Windows protected your PC", click **More info** → **Run anyway**.
  The PowerShell line above avoids this.
- **Linux:** unzip it, open a terminal in that folder and run `./sony-import`.
</details>

## How to use it

1. Put the memory card in your computer, and plug in the drive you back up to.
2. Open **Sony Import**: from Applications on a Mac, the Start menu on Windows, or the app menu on Linux.
3. **Choose your backup folder:** drag the folder into the window and press Enter. It can be any
   folder on any drive. Next time, just press Enter to reuse it.
4. Check what it found and type `y` to start copying.
5. **Planning to format the card?** Type `y` when it offers to check every file byte by byte.
   It tells you when it's safe to format the card in your camera.
6. When it says **All done**, type `y` to **eject the card**, then press Enter to close the window.

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

**Keeps your photos safe**
- Never changes your memory card. It only reads from it.
- Checks there's enough space on your backup drive before copying anything.
- Tells you when it's safe to format the card, after checking every file byte by byte.
- Safe to interrupt. If you close the window midway, just run it again to finish.
- Ejects the card for you when it's done, so you can take it straight out.

**Keeps them organised**
- Sorts everything by the date you took it, with videos in a `Videos` folder inside their day.
- Never copies the same photo twice, even if you renamed files in the backup or use several cards.
- Fills gaps: if a video or RAW + JPG photo is only half backed up, it copies just the missing half.
- Gives every file one clean number in shooting order (`DSC00001`…, `C00001`…), so names never clash.
- Shot in RAW + JPG? It offers to move the extra JPGs to the Trash, where you can restore them.

**Stays easy**
- One line to install on Windows, Mac or Linux, with no security warnings.
- Tells you when an update is out, with the line to install it.

## Good to know

- **Cameras:** works with Sony Alpha (a6000 series, a7 series…) and ZV cameras. Tested on the a6600.
- **Folder dates use the camera's clock**, so make sure it's set correctly.
- **Checking a full card takes about a minute** before copying starts. The byte-by-byte
  "safe to format" check takes about a minute for every 2 GB on the card, depending on your card
  reader.
- **Privacy:** your photos never leave your computer. The only internet use is a quick check with
  GitHub for a newer version. Set `SONY_IMPORT_NO_UPDATE_CHECK=1` to turn it off.

<details>
<summary>Uninstall</summary>

- **Mac:** drag **Sony Import** from Applications to the Trash.
- **Windows:** delete the folder `%LOCALAPPDATA%\Programs\Sony Import` and the **Sony Import**
  shortcut in the Start menu (right-click it → Open file location).
- **Linux:** delete `~/.local/bin/sony-import` and `~/.local/share/applications/sony-import.desktop`.

Your backup folder and photos are never touched. The app also keeps one small settings file, the
last backup folder you used, in `.sony-import.json` in your home folder. You can delete that too.
</details>

---

**[What's new](CHANGELOG.md)** in each version. Developers: see **[DEVELOPMENT.md](DEVELOPMENT.md)** for running from source, scripting, how it
works, and releasing. Licensed under [MIT](LICENSE).
