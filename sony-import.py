#!/usr/bin/env python3
"""Back up photos and videos from Sony camera cards into Year/Month/Day folders.

The card is only ever read, never written. "Already backed up" is decided by
scanning the destination itself (size + capture time + content sample), so
there is no state file and any destination folder works.

The backup folder comes from --dest, or the SONY_IMPORT_DEST environment variable.

Subcommands (all print human text; add --json for machine output):
  detect  [--dest DIR]                find Sony cards; check the backup drive
  plan    --dest DIR [--card PATH..]  report what is new on each card
  import  --dest DIR [--card PATH..]  copy new files (progress bar), write --report
  trash-jpgs --report FILE            move JPGs that have an ARW twin to the Trash
Run with no subcommand for a fully interactive session in a terminal.
"""
import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import string
import struct
import subprocess
import sys
import time
from datetime import datetime

__version__ = "1.1.0"
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
TRASH = "Recycle Bin" if IS_WIN else "Trash"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".sony-import.json")
DEFAULT_DEST = os.environ.get("SONY_IMPORT_DEST")  # backup folder; --dest overrides
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
PHOTO_EXT = {".ARW", ".JPG", ".JPEG", ".HIF", ".HEIF"}
SONY_DCIM_DIR = re.compile(r"^\d{3}(MSDCF|\d{5})$")
NUM_WIDTH = 5
CHUNK = 8 * 1024 * 1024


# ---------------------------------------------------------------- style
# Colour carries meaning: magenta = memory card, cyan = backup folder / structure,
# green = done & safe, yellow = needs attention, red = errors, dim = secondary detail.

def _enable_color():
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty() or os.environ.get("TERM") == "dumb":
        return False
    if not IS_WIN:
        return True
    try:  # Windows 10+: switch the console into ANSI mode
        import ctypes
        k = ctypes.windll.kernel32
        h, mode = k.GetStdHandle(-11), ctypes.c_uint32()
        return bool(k.GetConsoleMode(h, ctypes.byref(mode)) and k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


def _can_print(text):
    try:
        text.encode(sys.stdout.encoding or "ascii")
        return True
    except Exception:
        return False


COLOR = _enable_color()
FANCY = _can_print("█░✓✗⚠→·─┌┐└┘│›")
BOLD, DIM, RED, GREEN, YELLOW, MAGENTA, CYAN = "1", "2", "31", "32", "33", "35", "36"
DOT = "·" if FANCY else "-"
ARROW = "→" if FANCY else "->"


def paint(text, *codes):
    return f"\033[{';'.join(codes)}m{text}\033[0m" if COLOR and codes else str(text)


def card_path(p):
    return paint(p, BOLD, MAGENTA)


def dest_path(p):
    return paint(p, BOLD, CYAN)


def ok(text):
    return paint(("✓ " if FANCY else "") + text, BOLD, GREEN)


def warn(text):
    return paint(("⚠ " if FANCY else "! ") + text, BOLD, YELLOW)


def bad(text):
    return paint(("✗ " if FANCY else "x ") + text, BOLD, RED)


def dim(text):
    return paint(text, DIM)


def step(n, total, title):
    rule = "─" if FANCY else "-"
    head = f"{rule * 2} Step {n} of {total} {DOT} {title} "
    print("\n" + paint(head + rule * max(0, 60 - len(head)), BOLD, CYAN))


def nice_dt(dt):
    d = datetime.strptime(dt[:19], "%Y:%m:%d %H:%M:%S")
    return f"{d.day} {MONTHS[d.month][:3]} {d.year}, {d:%H:%M}"


def nice_secs(sec):
    sec = int(sec)
    return f"{sec}s" if sec < 60 else f"{sec // 60}m {sec % 60:02d}s"


# ---------------------------------------------------------------- metadata

def _tiff_datetime(f, base):
    """Return 'YYYY:MM:DD HH:MM:SS[.sub]' from a TIFF/EXIF block starting at base."""
    f.seek(base)
    head = f.read(8)
    if head[:2] == b"II":
        e = "<"
    elif head[:2] == b"MM":
        e = ">"
    else:
        return None

    def read_ifd(off):
        f.seek(base + off)
        n = struct.unpack(e + "H", f.read(2))[0]
        tags = {}
        for _ in range(n):
            tag, typ, cnt, val = struct.unpack(e + "HHI4s", f.read(12))
            tags[tag] = (typ, cnt, val)
        return tags

    def ascii_val(entry):
        typ, cnt, val = entry
        if cnt <= 4:
            raw = val[:cnt]
        else:
            pos = f.tell()
            f.seek(base + struct.unpack(e + "I", val)[0])
            raw = f.read(cnt)
            f.seek(pos)
        return raw.split(b"\0")[0].decode("ascii", "ignore").strip()

    ifd0 = read_ifd(struct.unpack(e + "I", head[4:8])[0])
    dt = sub = None
    if 0x8769 in ifd0:
        exif = read_ifd(struct.unpack(e + "I", ifd0[0x8769][2])[0])
        if 0x9003 in exif:
            dt = ascii_val(exif[0x9003])
        if 0x9291 in exif:
            sub = ascii_val(exif[0x9291])
    if not dt and 0x0132 in ifd0:
        dt = ascii_val(ifd0[0x0132])
    if not dt:
        return None
    return dt + ("." + sub if sub else "")


def _jpeg_datetime(f):
    f.seek(0)
    if f.read(2) != b"\xff\xd8":
        return None
    while True:
        marker = f.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        if marker[1] in (0xD9, 0xDA):
            return None
        length = struct.unpack(">H", f.read(2))[0]
        start = f.tell()
        if marker[1] == 0xE1 and f.read(6) == b"Exif\0\0":
            return _tiff_datetime(f, start + 6)
        f.seek(start + length - 2)


def _sips_datetime(path):
    if not IS_MAC:
        return None
    try:
        out = subprocess.run(["sips", "-g", "creation", path],
                             capture_output=True, text=True, timeout=30).stdout
        m = re.search(r"creation:\s*(\d{4}:\d\d:\d\d \d\d:\d\d:\d\d)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def _mtime_datetime(path):
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y:%m:%d %H:%M:%S")


def photo_datetime(path):
    ext = os.path.splitext(path)[1].upper()
    dt = None
    try:
        with open(path, "rb") as f:
            if ext == ".ARW":
                dt = _tiff_datetime(f, 0)
            elif ext in (".JPG", ".JPEG"):
                dt = _jpeg_datetime(f)
    except Exception:
        dt = None
    return dt or _sips_datetime(path) or _mtime_datetime(path)


def video_datetime(mp4, xml):
    if xml and os.path.exists(xml):
        try:
            with open(xml, "r", encoding="utf-8", errors="ignore") as f:
                m = re.search(r'<CreationDate value="(\d{4})-(\d\d)-(\d\d)T(\d\d:\d\d:\d\d)', f.read())
            if m:
                return f"{m.group(1)}:{m.group(2)}:{m.group(3)} {m.group(4)}"
        except Exception:
            pass
    return _mtime_datetime(mp4)


def fingerprint(path):
    """Hash of three 64 KB samples (start, middle, end): cheap, and tells apart
    burst shots that share size and capture second (Sony compressed RAW is fixed-size)."""
    size = os.path.getsize(path)
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for off in (0, size // 2, max(size - 65536, 0)):
            f.seek(off)
            h.update(f.read(65536))
    return h.hexdigest()


def video_xml_for(mp4):
    stem, _ = os.path.splitext(mp4)
    xml = stem + "M01.XML"
    return xml if os.path.exists(xml) else None


# ---------------------------------------------------------------- detection

def is_sony_card(root):
    dcim = os.path.join(root, "DCIM")
    if not os.path.isdir(dcim) or not os.path.isdir(os.path.join(root, "PRIVATE", "M4ROOT")):
        return False
    try:
        return any(SONY_DCIM_DIR.match(d) for d in os.listdir(dcim))
    except OSError:
        return False


def mounted_volumes():
    """Roots of mounted drives: E:\\ on Windows, /Volumes/X on macOS, /media/user/X on Linux."""
    if IS_WIN:
        return [f"{c}:\\" for c in string.ascii_uppercase[2:] if os.path.exists(f"{c}:\\")]
    if IS_MAC:
        bases = ["/Volumes"]
    else:
        user = getpass.getuser()
        bases = [f"/media/{user}", f"/run/media/{user}", "/media", "/mnt"]
    vols = []
    for base in bases:
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for n in names:
            root = os.path.join(base, n)
            if os.path.isdir(root) and root not in vols:
                vols.append(root)
    return vols


def drive_of(path):
    """Root of the external drive holding path, or None if it is on the internal disk."""
    path = os.path.abspath(path)
    if IS_WIN:
        d = os.path.splitdrive(path)[0]
        return d + "\\" if d and d.upper() != "C:" else None
    parts = path.split(os.sep)
    if IS_MAC:
        return os.sep.join(parts[:3]) if len(parts) > 2 and parts[1] == "Volumes" else None
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    if parts[1:4] == ["run", "media", user] and len(parts) > 4:
        return os.sep.join(parts[:5])
    if parts[1:3] == ["media", user] and len(parts) > 3:
        return os.sep.join(parts[:4])
    if len(parts) > 2 and parts[1] in ("media", "mnt"):
        return os.sep.join(parts[:3])
    return None


def detect(dest=None):
    cards = [v for v in mounted_volumes() if is_sony_card(v)]
    drive = drive_of(dest) if dest else None
    return {
        "cards": cards,
        "dest": dest,
        "dest_drive": drive,
        "dest_drive_connected": bool(dest) and (drive is None or os.path.isdir(drive)),
        "dest_exists": bool(dest) and os.path.isdir(dest),
    }


# ---------------------------------------------------------------- card scan

def scan_card(root):
    """Return list of items. An item is one photo, one ARW+JPG pair, or one video."""
    items = []
    dcim = os.path.join(root, "DCIM")
    for d in sorted(os.listdir(dcim)):
        folder = os.path.join(dcim, d)
        if not (os.path.isdir(folder) and SONY_DCIM_DIR.match(d)):
            continue
        by_stem = {}
        for fn in sorted(os.listdir(folder)):
            if fn.startswith("."):
                continue
            stem, ext = os.path.splitext(fn)
            if ext.upper() in PHOTO_EXT:
                by_stem.setdefault(stem, []).append(os.path.join(folder, fn))
        for stem, paths in by_stem.items():
            arw = [p for p in paths if p.upper().endswith(".ARW")]
            jpg = [p for p in paths if p.upper().endswith((".JPG", ".JPEG"))]
            other = [p for p in paths if p not in arw and p not in jpg]
            if arw and jpg:
                # JPG first: if the ARW made it to the backup, the JPG did too.
                files = jpg[:1] + arw[:1]
                items.append({"kind": "pair", "card": root, "files": files, "key_file": arw[0]})
                rest = jpg[1:] + arw[1:] + other
            else:
                rest = paths
            for p in rest:
                items.append({"kind": "photo", "card": root, "files": [p], "key_file": p})
    clip = os.path.join(root, "PRIVATE", "M4ROOT", "CLIP")
    if os.path.isdir(clip):
        for fn in sorted(os.listdir(clip)):
            if fn.startswith(".") or not fn.upper().endswith(".MP4"):
                continue
            mp4 = os.path.join(clip, fn)
            xml = video_xml_for(mp4)
            items.append({"kind": "video", "card": root,
                          "files": [mp4] + ([xml] if xml else []), "key_file": mp4})
    return items


def read_item(it):
    """The slow part: read capture time and a content fingerprint from the card."""
    if it["kind"] == "video":
        it["dt"] = video_datetime(it["key_file"], it["files"][1] if len(it["files"]) > 1 else None)
    else:
        it["dt"] = photo_datetime(it["key_file"])
    it["size"] = sum(os.path.getsize(p) for p in it["files"])
    it["key_size"] = os.path.getsize(it["key_file"])
    it["fp"] = fingerprint(it["key_file"])


# ---------------------------------------------------------------- destination scan

class DestIndex:
    """Files already in the destination, matched by size then capture time."""

    def __init__(self, dest):
        self.dest = dest
        self.by_size = {}
        self.max_photo = 0
        self.max_video = 0
        self.file_count = 0
        self._dt_cache = {}
        self._fp_cache = {}
        if not os.path.isdir(dest):
            return
        for dirpath, dirnames, filenames in os.walk(dest):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                ext = os.path.splitext(fn)[1].upper()
                if ext not in PHOTO_EXT and ext != ".MP4":
                    continue
                p = os.path.join(dirpath, fn)
                self.file_count += 1
                self.by_size.setdefault(os.path.getsize(p), []).append(p)
                m = re.match(r"^DSC(\d+)", fn, re.I)
                if m and ext in PHOTO_EXT:
                    self.max_photo = max(self.max_photo, int(m.group(1)))
                m = re.match(r"^C(\d+)", fn, re.I)
                if m and ext == ".MP4":
                    self.max_video = max(self.max_video, int(m.group(1)))

    def _dt(self, p):
        if p not in self._dt_cache:
            if p.upper().endswith(".MP4"):
                self._dt_cache[p] = video_datetime(p, video_xml_for(p))
            else:
                self._dt_cache[p] = photo_datetime(p)
        return self._dt_cache[p]

    def _fp(self, p):
        if p not in self._fp_cache:
            self._fp_cache[p] = fingerprint(p)
        return self._fp_cache[p]

    def contains(self, item):
        ext = os.path.splitext(item["key_file"])[1].upper()
        for p in self.by_size.get(item["key_size"], []):
            if (os.path.splitext(p)[1].upper() == ext and self._dt(p) == item["dt"]
                    and self._fp(p) == item["fp"]):
                return True
        return False


# ---------------------------------------------------------------- planning

def day_folder(dest, dt):
    d = datetime.strptime(dt[:19], "%Y:%m:%d %H:%M:%S")
    return os.path.join(dest, f"{d.year}", f"{d.month}. {MONTHS[d.month]}",
                        f"{d.day:02d}{MONTHS[d.month][:3]}{d.year % 100:02d}")


def build_plan(dest, cards):
    index = DestIndex(dest)
    new, seen_keys, per_card = [], set(), {}
    listed = [(card, scan_card(card)) for card in cards]
    bar = Bar(sum(len(items) for _, items in listed), "Checking", CYAN)
    for card, items in listed:
        stats = {"card": card, "photos_on_card": 0, "videos_on_card": 0,
                 "already_photos": 0, "already_videos": 0, "new_photos": 0, "new_videos": 0,
                 "new_bytes": 0, "from": None, "to": None}
        for it in items:
            read_item(it)
            bar.update(1)
            is_video = it["kind"] == "video"
            stats["videos_on_card" if is_video else "photos_on_card"] += len(it["files"]) if not is_video else 1
            key = (it["key_size"], it["dt"], it["fp"])
            if key in seen_keys or index.contains(it):
                stats["already_videos" if is_video else "already_photos"] += 1 if is_video else len(it["files"])
                continue
            seen_keys.add(key)
            new.append(it)
            stats["new_videos" if is_video else "new_photos"] += 1 if is_video else len(it["files"])
            stats["new_bytes"] += it["size"]
            stats["from"] = min(filter(None, [stats["from"], it["dt"]]))
            stats["to"] = max(filter(None, [stats["to"], it["dt"]]))
        per_card[card] = stats
    bar.finish()
    new.sort(key=lambda it: (it["dt"], it["key_file"]))
    photo_n, video_n = index.max_photo, index.max_video
    for it in new:
        folder = day_folder(dest, it["dt"])
        if it["kind"] == "video":
            video_n += 1
            base = f"C{video_n:0{NUM_WIDTH}d}"
            it["targets"] = []
            for src in it["files"]:
                if src.upper().endswith(".MP4"):
                    name = base + ".MP4"
                else:
                    name = base + "M01.XML"
                it["targets"].append(os.path.join(folder, "Videos", name))
        else:
            photo_n += 1
            base = f"DSC{photo_n:0{NUM_WIDTH}d}"
            it["targets"] = [os.path.join(folder, base + os.path.splitext(s)[1].upper())
                             for s in it["files"]]
    return {"dest": dest, "dest_existing_files": index.file_count,
            "cards": list(per_card.values()), "items": new}


# ---------------------------------------------------------------- copying

def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


class Bar:
    """One-line progress bar. Silent when not on a terminal, unless log=True
    (then it prints 'PROGRESS NN% ...' lines every 5% for scripts and logs)."""
    WIDTH = 28

    def __init__(self, total, label, color, nbytes=False, files_total=0, log=False):
        self.total, self.label, self.color = max(total, 1), label, color
        self.nbytes, self.files_total, self.log = nbytes, files_total, log
        self.done = self.files_done = 0
        self.tty = sys.stdout.isatty()
        self.start = time.time()
        self.last_draw, self.last_pct = 0.0, -5

    def update(self, n=0, file_done=False):
        self.done += n
        self.files_done += 1 if file_done else 0
        if self.tty:
            if time.time() - self.last_draw >= 0.08:
                self._draw()
        elif self.log:
            pct = int(self.done * 100 / self.total)
            if pct >= self.last_pct + 5 or (file_done and self.files_done == self.files_total):
                print(f"PROGRESS {pct}% {self.files_done}/{self.files_total} files "
                      f"{human(self.done)}/{human(self.total)}", flush=True)
                self.last_pct = pct

    def _draw(self):
        self.last_draw = time.time()
        frac = min(self.done / self.total, 1.0)
        full = int(frac * self.WIDTH)
        if FANCY:
            bar = paint("█" * full, self.color) + paint("░" * (self.WIDTH - full), DIM)
        else:
            bar = "[" + paint("#" * full, self.color) + "-" * (self.WIDTH - full) + "]"
        details = []  # (priority, text): lowest priority is dropped first on narrow windows
        if self.nbytes:
            details.append((4, f"{self.files_done}/{self.files_total} files"))
            details.append((2, f"{human(self.done)} of {human(self.total)}"))
            elapsed = time.time() - self.start
            if elapsed > 1 and self.done:
                speed = self.done / elapsed
                details.append((1, f"{human(speed)}/s"))
                details.append((3, f"{nice_secs((self.total - self.done) / speed)} left"))
        else:
            details.append((4, f"{self.done} of {self.total} files"))
        cols = shutil.get_terminal_size((80, 24)).columns
        fixed = 2 + len(self.label) + 1 + self.WIDTH + (0 if FANCY else 2) + 6
        while details and fixed + len(f" {DOT} ".join(t for _, t in details)) + 1 > cols:
            details.remove(min(details))
        details = [t for _, t in details]
        line = (f"  {paint(self.label, BOLD)} {bar} {paint(f'{int(frac * 100):3d}%', BOLD)}  "
                + dim(f" {DOT} ".join(details)))
        sys.stdout.write("\r" + line + ("\033[K" if COLOR else ""))
        sys.stdout.flush()

    def finish(self):
        if self.tty:
            self._draw()
            sys.stdout.write("\n")
            sys.stdout.flush()
        return time.time() - self.start


def copy_file(src, dst, progress):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".partial"
    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                buf = fi.read(CHUNK)
                if not buf:
                    break
                fo.write(buf)
                progress.update(len(buf))
    except BaseException:  # includes Ctrl-C: never leave half-written files behind
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    st = os.stat(src)
    os.utime(tmp, (st.st_atime, st.st_mtime))
    if os.path.getsize(tmp) != st.st_size:
        os.remove(tmp)
        raise IOError(f"size mismatch copying {src}")
    os.rename(tmp, dst)
    progress.update(0, file_done=True)


def run_import(plan):
    items = plan["items"]
    total_files = sum(len(it["files"]) for it in items)
    progress = Bar(sum(it["size"] for it in items), "Copying", GREEN, nbytes=True,
                   files_total=total_files, log=True)
    copied, errors, pairs = [], [], []
    for it in items:
        try:
            for src, dst in zip(it["files"], it["targets"]):
                if os.path.exists(dst):
                    raise IOError(f"target already exists: {dst}")
                copy_file(src, dst, progress)
                copied.append({"src": src, "dst": dst, "dt": it["dt"]})
            if it["kind"] == "pair":
                jpg = next(t for t in it["targets"] if t.upper().endswith((".JPG", ".JPEG")))
                arw = next(t for t in it["targets"] if t.upper().endswith(".ARW"))
                pairs.append({"arw": arw, "jpg": jpg})
        except Exception as e:
            errors.append({"files": it["files"], "error": str(e)})
    seconds = progress.finish()
    by_day = {}
    for f in sorted(copied, key=lambda f: f["dt"]):
        day = os.path.relpath(day_folder(plan["dest"], f["dt"]), plan["dest"])
        kind = "videos" if f["dst"].upper().endswith(".MP4") else (
            "xml" if f["dst"].upper().endswith(".XML") else "photos")
        by_day.setdefault(day, {"photos": 0, "videos": 0, "xml": 0})[kind] += 1
    return {"dest": plan["dest"], "copied": copied, "errors": errors,
            "raw_jpg_pairs": pairs, "by_day": by_day, "seconds": round(seconds, 1)}


def _windows_drive_is_removable(path):
    import ctypes
    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    return ctypes.windll.kernel32.GetDriveTypeW(root) == 2  # DRIVE_REMOVABLE


def trash(paths):
    """Move files to the Trash / Recycle Bin so they can be recovered. Never deletes outright."""
    moved = []
    for i in range(0, len(paths), 100):
        batch = [p for p in paths[i:i + 100] if os.path.exists(p)]
        if not batch:
            continue
        if IS_MAC:
            files = ", ".join('POSIX file "%s"' % p.replace('"', '\\"') for p in batch)
            cmd = ["osascript", "-e", f'tell application "Finder" to delete {{{files}}}']
        elif IS_WIN:
            # Removable drives have no Recycle Bin: Windows would delete permanently.
            if _windows_drive_is_removable(batch[0]):
                raise RuntimeError("this drive has no Recycle Bin, so the JPGs were left in place")
            script = "Add-Type -AssemblyName Microsoft.VisualBasic; " + "; ".join(
                "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('%s', 'OnlyErrorDialogs', "
                "'SendToRecycleBin')" % p.replace("'", "''") for p in batch)
            cmd = ["powershell", "-NoProfile", "-Command", script]
        elif shutil.which("gio"):
            cmd = ["gio", "trash"] + batch
        elif shutil.which("trash-put"):
            cmd = ["trash-put"] + batch
        else:
            raise RuntimeError("no Trash tool found (install 'gio' or 'trash-cli'); JPGs were left in place")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "moving to the Trash failed")
        moved += batch
    return moved


# ---------------------------------------------------------------- printing

def counts(p, v):
    parts = [f"{p} photo{'s' * (p != 1)}"] if p else []
    parts += [f"{v} video{'s' * (v != 1)}"] if v else []
    return ", ".join(parts)


def _mark(kind):
    if kind == "ok":
        return paint("✓" if FANCY else "OK", BOLD, GREEN)
    if kind == "warn":
        return paint("⚠" if FANCY else "!", BOLD, YELLOW)
    return paint("✗" if FANCY else "x", BOLD, RED)


def _row(name, value, width=19):
    print("    " + dim(name.ljust(width)) + value)


def _day(rel):
    head, day = os.path.split(rel)
    return dim(head + os.sep) + paint(day, BOLD, CYAN), len(rel)


def print_days(rows):
    """rows: list of (relative day folder, text). Prints an aligned list."""
    width = max(len(rel) for rel, _ in rows)
    for rel, text in rows:
        styled, n = _day(rel)
        print("    " + styled + " " * (width - n + 3) + text)


def print_detect(info):
    if info["cards"]:
        for c in info["cards"]:
            print(f"  {_mark('ok')} Memory card    " + card_path(c))
    else:
        print(f"  {_mark('bad')} Memory card    " + paint("not found", YELLOW))
    if not info["dest"]:
        print(f"  {_mark('bad')} Backup folder  " + paint("not set (use --dest or SONY_IMPORT_DEST)", YELLOW))
        return
    if info["dest_drive"]:
        if info["dest_drive_connected"]:
            print(f"  {_mark('ok')} Backup drive   " + dest_path(info["dest_drive"]))
        else:
            print(f"  {_mark('bad')} Backup drive   " + dest_path(info["dest_drive"])
                  + paint("  not connected", YELLOW))
    if info["dest_drive_connected"]:
        state = _mark("ok") if info["dest_exists"] else _mark("warn")
        note = "" if info["dest_exists"] else paint("  will be created", YELLOW)
        print(f"  {state} Backup folder  " + dest_path(info["dest"]) + note)


def print_plan(plan):
    print("\n  " + paint("Backup folder", BOLD) + "  " + dest_path(plan["dest"])
          + dim(f"  {DOT} {plan['dest_existing_files']} files already there"))
    for s in plan["cards"]:
        print("\n  " + paint("Memory card", BOLD) + "    " + card_path(s["card"]))
        _row("On card", counts(s["photos_on_card"], s["videos_on_card"]) or "nothing")
        already = counts(s["already_photos"], s["already_videos"])
        _row("Already backed up", paint(already, GREEN) if already else dim("nothing"))
        if s["new_photos"] or s["new_videos"]:
            _row("New", paint(counts(s["new_photos"], s["new_videos"]), BOLD, YELLOW)
                 + dim(f"  {DOT} {human(s['new_bytes'])}"))
            _row("Shot between", f"{nice_dt(s['from'])}  {dim(ARROW)}  {nice_dt(s['to'])}")
        else:
            _row("New", ok("nothing, all backed up"))
    days = {}
    for it in plan["items"]:  # items are already in capture order
        day = os.path.relpath(day_folder(plan["dest"], it["dt"]), plan["dest"])
        d = days.setdefault(day, [0, 0])
        d[1 if it["kind"] == "video" else 0] += 1 if it["kind"] == "video" else len(it["files"])
    if days:
        print("\n  " + paint("Will be copied into", BOLD))
        print_days([(day, counts(p, v)) for day, (p, v) in days.items()])


def print_report(rep):
    print()
    took = f" in {nice_secs(rep['seconds'])}" if rep.get("seconds", 0) >= 1 else ""
    photos = sum(c["photos"] for c in rep["by_day"].values())
    videos = sum(c["videos"] for c in rep["by_day"].values())
    print("  " + ok(f"Copied {counts(photos, videos).replace(', ', ' and ') or 'nothing'}{took}"))
    if rep["by_day"]:
        print_days([(day, counts(c["photos"], c["videos"])) for day, c in rep["by_day"].items()])
    if rep["errors"]:
        print("\n  " + bad(f"{len(rep['errors'])} could not be copied:"))
        for e in rep["errors"]:
            print("    " + paint(os.path.basename(e["files"][0]), RED) + dim(f"  {e['error']}"))
    if rep["raw_jpg_pairs"]:
        n = len(rep["raw_jpg_pairs"])
        print("\n  " + warn(f"{n} photo{'s were' if n != 1 else ' was'} shot as RAW + JPG"))
        rows = []
        for p in rep["raw_jpg_pairs"]:
            rel = os.path.relpath(p["arw"], rep["dest"])
            rows.append((os.path.dirname(rel), os.path.splitext(os.path.basename(rel))[0]
                         + dim("  .ARW + .JPG")))
        print_days(rows)


# ---------------------------------------------------------------- CLI

def ask(q):
    try:
        return input(q).strip()
    except EOFError:
        return ""


def prompt(question, keys=()):
    """Ask a question; keys is a list of (key, meaning) shown as coloured hints."""
    hint = "  ".join(f"{paint('[' + k + ']', BOLD, CYAN)} {meaning}" for k, meaning in keys)
    arrow = paint("›" if FANCY else ">", BOLD, CYAN)
    return ask(f"\n  {paint(question, BOLD)}  {hint}  {arrow} ")


def yes(question):
    return prompt(question, [("y", "yes"), ("n", "no")]).lower() in ("y", "yes")


def clean_path(text):
    """Accept a typed path or a folder dragged into the window (quoted or backslash-escaped)."""
    t = text.strip()
    if t.startswith("& "):  # PowerShell drag-and-drop
        t = t[2:].strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        t = t[1:-1]
    elif not IS_WIN:
        t = re.sub(r"\\(.)", r"\1", t)  # "My\ SSD" -> "My SSD"
    return os.path.abspath(os.path.expanduser(t)) if t else ""


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def banner():
    title, sub = "SONY IMPORT", "Back up your camera card, sorted by date"
    ver = f"v{__version__}"
    width = max(len(title) + len(ver) + 4, len(sub)) + 4
    if FANCY:
        edge = paint("│", CYAN)
        print("\n  " + paint("┌" + "─" * width + "┐", CYAN))
        gap = width - 2 - len(title) - len(ver)
        print(f"  {edge}  {paint(title, BOLD, CYAN)}{' ' * (gap - 2)}{dim(ver)}  {edge}")
        print(f"  {edge}  {dim(sub)}{' ' * (width - 2 - len(sub))}{edge}")
        print("  " + paint("└" + "─" * width + "┘", CYAN))
    else:
        print(f"\n  {paint(title, BOLD, CYAN)}  {dim(ver)}\n  {dim(sub)}")


def choose_dest(current):
    example = "E:\\Photos\\Sony Backup" if IS_WIN else "/Volumes/MySSD/Photos/Sony Backup"
    print("\n  " + paint("Where should the backup go?", BOLD))
    print("  " + dim("Type the folder path, or drag the folder into this window, then press Enter."))
    if current:
        print("  " + dim("Press Enter to keep ") + dest_path(current))
    else:
        print("  " + dim("Example: " + example))
    a = ask("  " + paint("›" if FANCY else ">", BOLD, CYAN) + " ")
    return clean_path(a) if a else current


STEPS = 4


def interactive(dest):
    banner()
    cfg = load_config()
    dest = dest or cfg.get("dest")
    if not dest:
        dest = choose_dest(None)
        if not dest:
            return 0

    step(1, STEPS, "Connect")
    while True:  # wait until the card and the backup drive are both plugged in
        info = detect(dest)
        print_detect(info)
        if info["cards"] and info["dest_drive_connected"]:
            break
        a = prompt("Plug it in, then press Enter to check again.", [("q", "quit")])
        if a.lower() == "q":
            return 1
        print()

    step(2, STEPS, "Confirm")
    while True:
        for c in info["cards"]:
            print("  " + dim("From ") + " " + card_path(c) + dim("   memory card"))
        print("  " + dim("To   ") + " " + dest_path(dest) + dim("   backup folder"))
        a = prompt("Is this right?", [("y", "yes"), ("c", "change folder"), ("q", "quit")]).lower()
        if a in ("q", "n", "no"):
            return 0
        if a in ("y", "yes"):
            drive = drive_of(dest)
            if drive and not os.path.isdir(drive):
                print("\n  " + warn(f"The drive {drive} is not connected. Plug it in or pick another folder."))
                print()
                continue
            break
        if a == "c":
            dest = choose_dest(dest)
            print()

    if not os.path.isdir(dest):
        if not yes(f"The folder does not exist yet. Create it?"):
            return 0
        os.makedirs(dest)
    save_config({**cfg, "dest": dest})

    step(3, STEPS, "Check what's new")
    plan = build_plan(dest, info["cards"])
    print_plan(plan)
    if not plan["items"]:
        print("\n  " + ok("Everything on the card is already backed up. Nothing to do."))
        return 0
    if not yes("Start copying?"):
        return 0

    step(4, STEPS, "Copy")
    rep = run_import(plan)
    print_report(rep)
    if rep["raw_jpg_pairs"]:
        print("  " + dim("You have the RAW file for each of these, so the JPGs are extra copies."))
        if yes(f"Move these JPGs to the {TRASH}?"):
            try:
                moved = trash([p["jpg"] for p in rep["raw_jpg_pairs"]])
                print("\n  " + ok(f"Moved {len(moved)} JPGs to the {TRASH}. You can restore them from there."))
            except Exception as e:
                print("\n  " + bad(f"Could not move the JPGs: {e}"))
    if rep["errors"]:
        print("\n  " + bad("Some files were not copied. Run Sony Import again to retry them."))
    else:
        print("\n  " + ok("All done. You can safely remove the memory card."))
    return 1 if rep["errors"] else 0


def run_interactive(dest):
    """Wrapper for double-click use: show errors and keep the window open at the end."""
    code = 1
    try:
        code = interactive(dest)
    except KeyboardInterrupt:
        print("\n\n  " + warn("Stopped. Nothing half-copied was left behind; run again to finish."))
    except Exception as e:
        print("\n\n  " + bad(f"Something went wrong: {e}"))
    ask("\n  " + dim("Press Enter to close this window."))
    return code


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"sony-import {__version__}")
    ap.add_argument("--dest", default=DEFAULT_DEST, help="backup folder (interactive mode)")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("detect")
    p.add_argument("--dest", default=DEFAULT_DEST)
    p.add_argument("--json", action="store_true")
    for name in ("plan", "import"):
        p = sub.add_parser(name)
        p.add_argument("--dest", default=DEFAULT_DEST)
        p.add_argument("--card", action="append", help="card root; default: all detected")
        p.add_argument("--json", action="store_true")
        if name == "import":
            p.add_argument("--report", help="write the final report JSON here")
    p = sub.add_parser("trash-jpgs", help="move JPGs that have an ARW twin to the Trash")
    p.add_argument("--report", required=True)
    args = ap.parse_args()

    if args.cmd is None:
        return run_interactive(args.dest)
    if args.cmd == "detect":
        info = detect(args.dest)
        print(json.dumps(info, indent=2)) if args.json else print_detect(info)
        return 0
    if args.cmd == "trash-jpgs":
        with open(args.report) as f:
            rep = json.load(f)
        moved = trash([p["jpg"] for p in rep["raw_jpg_pairs"]])
        print(f"Moved {len(moved)} JPGs to the Trash.")
        return 0

    if not args.dest:
        print("No backup folder: pass --dest or set SONY_IMPORT_DEST.", file=sys.stderr)
        return 2
    cards = args.card or detect()["cards"]
    for c in cards:
        if not is_sony_card(c):
            print(f"Not a Sony camera card: {c}", file=sys.stderr)
            return 2
    if not cards:
        print("No Sony camera card found.", file=sys.stderr)
        return 2
    plan = build_plan(os.path.abspath(args.dest), cards)
    if args.cmd == "plan":
        if args.json:
            slim = {k: v for k, v in plan.items() if k != "items"}
            slim["new_items"] = len(plan["items"])
            print(json.dumps(slim, indent=2))
        else:
            print_plan(plan)
        return 0
    if not plan["items"]:
        print("Nothing new to back up.")
        return 0
    rep = run_import(plan)
    print_report(rep)
    if args.report:
        with open(args.report, "w") as f:
            json.dump(rep, f, indent=2)
        print(f"\nReport written to {args.report}")
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
