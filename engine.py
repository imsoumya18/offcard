#!/usr/bin/env python3
"""ShotLoft engine: backs up Sony camera cards into Year/Month/Day folders.

This is the engine behind the ShotLoft desktop app (shotloft.py), which loads it at
start-up. Its commands below are internal: the app's tests and scripts use them. Users use the app.

The card is only ever read, never written. "Already backed up" is decided by scanning the backup
folder itself (each file by size + a content fingerprint), so there is no state file.

Internal commands (--json for machine output; --dest can come from SHOTLOFT_DEST):
  detect  [--dest DIR]                find Sony cards; check the backup drive
  plan    --dest DIR [--card PATH..]  what is new on each card
  import  --dest DIR [--card PATH..]  copy new files, write --report
  verify  --dest DIR [--card PATH..]  byte-for-byte check: safe to format?
  eject   [--card PATH..]             safely eject cards
  check-update                        is a newer release out?
  trash-jpgs --report FILE            move JPGs that have an ARW twin to the Trash
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

__version__ = "2.1.1"
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
TRASH = "Recycle Bin" if IS_WIN else "Trash"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".shotloft.json")
OLD_CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".sony-import.json")  # ShotLoft was called Sony Import
DEFAULT_DEST = os.environ.get("SHOTLOFT_DEST")  # backup folder; --dest overrides
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
PHOTO_EXT = {".ARW", ".JPG", ".JPEG", ".HIF", ".HEIF"}
SONY_DCIM_DIR = re.compile(r"^\d{3}(MSDCF|\d{5})$")
NUM_WIDTH = 5
CHUNK = 8 * 1024 * 1024


# ---------------------------------------------------------------- style
# Colour carries meaning, and every colour is readable on both dark and light terminals
# (contrast >= ~3.5:1 on black and on white; macOS Terminal's default theme is white):
#   teal   = structure: banner, step headings, both progress bars, prompt keys
#   orange = needs attention: new files, warnings, missing drives
#   green  = success: ticks, already backed up, copied, all done
#   red    = errors only
#   bold default text = content (paths, day folders); dim = labels and secondary detail

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
BOLD, DIM = "1", "2"
ACCENT = "38;5;30"   # teal   #008787
ATTN = "38;5;166"    # orange #d75f00
GOOD = "38;5;28"     # green  #008700
BAD = "38;5;167"     # red    #d75f5f
DOT = "·" if FANCY else "-"
ARROW = "→" if FANCY else "->"


def paint(text, *codes):
    return f"\033[{';'.join(codes)}m{text}\033[0m" if COLOR and codes else str(text)


def card_path(p):
    return paint(p, BOLD)


def dest_path(p):
    return paint(p, BOLD)


def ok(text):
    return paint(("✓ " if FANCY else "") + text, BOLD, GOOD)


def warn(text):
    return paint(("⚠ " if FANCY else "! ") + text, BOLD, ATTN)


def bad(text):
    return paint(("✗ " if FANCY else "x ") + text, BOLD, BAD)


def dim(text):
    return paint(text, DIM)


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
    it["sizes"] = [os.path.getsize(p) for p in it["files"]]
    it["fps"] = [fingerprint(p) for p in it["files"]]
    it["size"] = sum(it["sizes"])
    k = it["files"].index(it["key_file"])
    it["key"] = (it["sizes"][k], it["fps"][k])


# ---------------------------------------------------------------- destination scan

class DestIndex:
    """Files already in the destination, matched one by one by size + content fingerprint.
    Names and dates in the backup don't matter, so renamed or re-dated files still match."""

    def __init__(self, dest):
        self.dest = dest
        self.by_size = {}
        self.max_photo = 0
        self.max_video = 0
        self.file_count = 0  # photos + videos, for display
        self._fp_cache = {}
        if not os.path.isdir(dest):
            return
        for dirpath, dirnames, filenames in os.walk(dest):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                ext = os.path.splitext(fn)[1].upper()
                if ext not in PHOTO_EXT and ext not in (".MP4", ".XML"):
                    continue
                p = os.path.join(dirpath, fn)
                self.by_size.setdefault(os.path.getsize(p), []).append(p)
                if ext != ".XML":
                    self.file_count += 1
                m = re.match(r"^DSC(\d+)", fn, re.I)
                if m and ext in PHOTO_EXT:
                    self.max_photo = max(self.max_photo, int(m.group(1)))
                m = re.match(r"^C(\d+)", fn, re.I)
                if m and ext in (".MP4", ".XML"):  # count orphan XMLs too, so numbers never collide
                    self.max_video = max(self.max_video, int(m.group(1)))

    def find_all(self, size, fp, ext):
        """Paths in the backup that match a card file by size + fingerprint."""
        found = []
        for p in self.by_size.get(size, []):
            if os.path.splitext(p)[1].upper() != ext:
                continue
            if p not in self._fp_cache:
                self._fp_cache[p] = fingerprint(p)
            if self._fp_cache[p] == fp:
                found.append(p)
        return found

    def find(self, size, fp, ext):
        """Path of the backed-up copy of a card file, or None."""
        found = self.find_all(size, fp, ext)
        return found[0] if found else None


# ---------------------------------------------------------------- planning

def day_folder(dest, dt):
    d = datetime.strptime(dt[:19], "%Y:%m:%d %H:%M:%S")
    return os.path.join(dest, f"{d.year}", f"{d.month}. {MONTHS[d.month]}",
                        f"{d.day:02d}{MONTHS[d.month][:3]}{d.year % 100:02d}")


def item_counts(it):
    """(photos, videos, lone XMLs) that this item will copy."""
    up = [f.upper() for f in it["files"]]
    videos = sum(f.endswith(".MP4") for f in up)
    xmls = sum(f.endswith(".XML") for f in up)
    return len(up) - videos - xmls, videos, xmls if not videos else 0


def companion_target(found, src):
    """Where a missing half goes: next to its backed-up partner, with the partner's number.
    C00005.MP4 <-> C00005M01.XML, DSC00007.JPG <-> DSC00007.ARW."""
    folder, name = os.path.split(found)
    stem, ext = os.path.splitext(name)
    if ext.upper() == ".XML" and stem.upper().endswith("M01"):
        stem = stem[:-3]
    src_ext = os.path.splitext(src)[1].upper()
    return os.path.join(folder, stem + ("M01.XML" if src_ext == ".XML" else src_ext))


def check_item(it, index):
    """Return ('done', None) | ('new', None) | ('fill', [(src, target), ...])."""
    exts = [os.path.splitext(f)[1].upper() for f in it["files"]]
    found = [index.find(sz, fp, ext) for sz, fp, ext in zip(it["sizes"], it["fps"], exts)]
    if it["kind"] == "pair":
        jpg, arw = found  # files are [JPG, ARW]
        if arw:
            return "done", None  # JPG may have been moved to the Trash on purpose
        if jpg:
            return "fill", [(it["files"][1], companion_target(jpg, it["files"][1]))]
        return "new", None
    if all(found):
        return "done", None
    if any(found):
        anchor = next(f for f in found if f)
        return "fill", [(src, companion_target(anchor, src))
                        for src, f in zip(it["files"], found) if not f]
    return "new", None


SPACE_MARGIN = 50 * 1024 * 1024  # keep a little room for folder entries and the file system


def free_bytes(path):
    """Free space on the drive that holds path. The folder itself may not exist yet."""
    if os.environ.get("SHOTLOFT_TEST_FREE_BYTES"):  # test hook: pretend the drive is this full
        return int(os.environ["SHOTLOFT_TEST_FREE_BYTES"])
    p = os.path.abspath(path)
    while not os.path.exists(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    return shutil.disk_usage(p).free


def build_plan(dest, cards):
    index = DestIndex(dest)
    new, fills, seen_keys, per_card = [], [], set(), {}
    listed = [(card, scan_card(card)) for card in cards]
    bar = Bar(sum(len(items) for _, items in listed), "Checking", ACCENT)
    for card, items in listed:
        stats = {"card": card, "photos_on_card": 0, "videos_on_card": 0,
                 "already_photos": 0, "already_videos": 0, "new_photos": 0, "new_videos": 0,
                 "new_xml": 0, "repairs": 0, "new_bytes": 0, "from": None, "to": None}
        for it in items:
            read_item(it)
            bar.update(1)
            is_video = it["kind"] == "video"
            on_card = 1 if is_video else len(it["files"])
            stats["videos_on_card" if is_video else "photos_on_card"] += on_card
            state, copies = ("done", None) if it["key"] in seen_keys else check_item(it, index)
            seen_keys.add(it["key"])
            if state == "done":
                stats["already_videos" if is_video else "already_photos"] += on_card
                continue
            if state == "fill":
                srcs = [src for src, _ in copies]
                sizes = dict(zip(it["files"], it["sizes"]))
                it = dict(it, files=srcs, targets=[t for _, t in copies],
                          size=sum(sizes[f] for f in srcs), repair=True)
                if it["kind"] == "pair":
                    it["pair"] = (it["targets"][0], companion_target(it["targets"][0], "x.JPG"))
                fills.append(it)
                stats["repairs"] += len(srcs)
                if is_video:
                    stats["already_videos"] += 0 if any(f.upper().endswith(".MP4") for f in srcs) else 1
                else:
                    stats["already_photos"] += on_card - len(srcs)
            else:
                new.append(it)
            p, v, x = item_counts(it)
            stats["new_photos"] += p
            stats["new_videos"] += v
            stats["new_xml"] += x
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
            it["targets"] = [os.path.join(folder, "Videos", base + (".MP4" if src.upper().endswith(".MP4")
                                                                    else "M01.XML"))
                             for src in it["files"]]
        else:
            photo_n += 1
            base = f"DSC{photo_n:0{NUM_WIDTH}d}"
            it["targets"] = [os.path.join(folder, base + os.path.splitext(s)[1].upper())
                             for s in it["files"]]
            if it["kind"] == "pair":
                it["pair"] = (it["targets"][1], it["targets"][0])
    items = sorted(new + fills, key=lambda it: (it["dt"], it["key_file"]))
    needed, free = sum(it["size"] for it in items), free_bytes(dest)
    return {"dest": dest, "dest_existing_files": index.file_count,
            "cards": list(per_card.values()), "items": items,
            "needed_bytes": needed, "free_bytes": free,
            "enough_space": not items or needed + SPACE_MARGIN <= free}


# ---------------------------------------------------------------- copying

def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


PROGRESS_HOOK = None  # set by the desktop app: hook(label, done, total, files_done, files_total, nbytes, elapsed)


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
        if PROGRESS_HOOK:
            PROGRESS_HOOK(self.label, self.done, self.total, self.files_done, self.files_total,
                          self.nbytes, time.time() - self.start)
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
            if elapsed > 1 and 0 < self.done < self.total:
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
    progress = Bar(sum(it["size"] for it in items), "Copying", ACCENT, nbytes=True,
                   files_total=total_files, log=True)
    copied, errors, pairs, done = [], [], [], []
    for it in items:
        try:
            for src, dst in zip(it["files"], it["targets"]):
                if os.path.exists(dst):
                    raise IOError(f"target already exists: {dst}")
                copy_file(src, dst, progress)
                copied.append({"src": src, "dst": dst, "dt": it["dt"]})
            if "pair" in it:
                pairs.append({"arw": it["pair"][0], "jpg": it["pair"][1]})
            done.append(it)
        except Exception as e:
            errors.append({"files": it["files"], "error": str(e)})
    seconds = progress.finish()
    by_day = {}
    for it in done:  # already in capture order
        day = by_day.setdefault(item_folder(plan["dest"], it), {"photos": 0, "videos": 0, "xml": 0})
        for key, n in zip(("photos", "videos", "xml"), item_counts(it)):
            day[key] += n
    return {"dest": plan["dest"], "copied": copied, "errors": errors,
            "raw_jpg_pairs": pairs, "by_day": by_day, "seconds": round(seconds, 1)}


# ---------------------------------------------------------------- verification

def same_bytes(a, b, bar=None):
    """True if two files are byte-for-byte identical. Reports a's size to the bar either way."""
    size, done = os.path.getsize(a), 0
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                x, y = fa.read(CHUNK), fb.read(CHUNK)
                if x != y:
                    return False
                if not x:
                    return True
                done += len(x)
                if bar:
                    bar.update(len(x))
    finally:
        if bar and size > done:
            bar.update(size - done)


def verify(dest, cards, quiet=False):
    """Check that every file on the cards has a byte-for-byte identical copy in the backup."""
    index = DestIndex(dest)
    listed = [(card, scan_card(card)) for card in cards]
    bar = Bar(sum(len(items) for _, items in listed), "Checking", ACCENT)
    jobs, per_card = [], []
    for card, items in listed:
        st = {"card": card, "files": 0, "verified": 0, "missing": [], "different": [], "trashed_jpg": []}
        per_card.append(st)
        for it in items:
            read_item(it)
            bar.update(1)
            exts = [os.path.splitext(f)[1].upper() for f in it["files"]]
            cands = [index.find_all(sz, fp, ext) for sz, fp, ext in zip(it["sizes"], it["fps"], exts)]
            for i, (src, sz) in enumerate(zip(it["files"], it["sizes"])):
                st["files"] += 1
                if cands[i]:
                    jobs.append((st, src, cands[i], sz))
                elif it["kind"] == "pair" and i == 0 and cands[1]:
                    st["trashed_jpg"].append(src)  # JPG removed on purpose; its RAW is checked
                else:
                    st["missing"].append(src)
    bar.finish()
    vbar = Bar(sum(j[3] for j in jobs), "Verifying", ACCENT, nbytes=True, files_total=len(jobs),
               log=not quiet)
    for st, src, cands, _ in jobs:
        if same_bytes(src, cands[0], vbar) or any(same_bytes(src, c) for c in cands[1:]):
            st["verified"] += 1
        else:
            st["different"].append(src)
        vbar.update(0, file_done=True)
    seconds = vbar.finish()
    return {"dest": dest, "cards": per_card, "seconds": round(seconds, 1),
            "safe": all(not st["missing"] and not st["different"] for st in per_card)}


def print_verify(res):
    print()
    for st in res["cards"]:
        problems = [(f, "not in the backup") for f in st["missing"]] + \
                   [(f, "backup copy is different (damaged?)") for f in st["different"]]
        if not problems:
            print("  " + ok(f"All {st['files']} files on {st['card']} are safely backed up, byte for byte."))
            print("    " + paint("You can format this card in the camera.", BOLD))
        else:
            n = len(problems)
            print("  " + bad(f"{n} file{'s are' if n != 1 else ' is'} not safely backed up "
                             f"from {st['card']}. Don't format this card yet."))
            for f, why in problems[:20]:
                print("    " + paint(os.path.basename(f), BOLD) + dim(f"  {why}"))
            if n > 20:
                print("    " + dim(f"... and {n - 20} more"))
            print("    " + dim("Run ShotLoft again to copy them, then check again."))
        if st["trashed_jpg"]:
            n = len(st["trashed_jpg"])
            print("    " + dim(f"{n} JPG{'s' * (n != 1)} not in the backup because you moved "
                             f"{'them' if n != 1 else 'it'} to the {TRASH}; the RAW "
                             f"file{'s are' if n != 1 else ' is'} safe."))


# ---------------------------------------------------------------- eject

FILE_MANAGER = "Finder" if IS_MAC else "File Explorer" if IS_WIN else "your file manager"


def eject(root):
    """Safely eject a memory card (never formats or deletes). Returns (ejected, details)."""
    root = os.path.abspath(root)
    if not os.path.ismount(root):  # only ever eject a whole card, never the drive a folder sits on
        return False, "not the top of a mounted drive"
    try:
        if IS_MAC:
            r = subprocess.run(["diskutil", "eject", root], capture_output=True, text=True, timeout=60)
            return r.returncode == 0 and not os.path.exists(root), (r.stderr or r.stdout).strip()
        if IS_WIN:
            drive = os.path.splitdrive(root)[0]  # "E:"
            ps = f"(New-Object -ComObject Shell.Application).Namespace(17).ParseName('{drive}').InvokeVerb('Eject')"
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
            for _ in range(20):  # the Eject verb reports nothing, so wait for the drive to go away
                if not os.path.exists(drive + "\\"):
                    return True, ""
                time.sleep(0.5)
            return False, "Windows didn't eject the drive (is a file on it still open?)"
        if shutil.which("gio"):
            r = subprocess.run(["gio", "mount", "-e", root], capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                return True, ""
        if shutil.which("udisksctl") and shutil.which("findmnt"):
            dev = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "--target", root],
                                 capture_output=True, text=True).stdout.strip()
            if dev:
                r = subprocess.run(["udisksctl", "unmount", "-b", dev], capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    subprocess.run(["udisksctl", "power-off", "-b", dev], capture_output=True, timeout=60)
                    return True, ""
                return False, (r.stderr or r.stdout).strip()
        return False, "no eject tool found (gio or udisksctl)"
    except Exception as e:
        return False, str(e)


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

def counts(p, v, x=0):
    parts = [f"{p} photo{'s' * (p != 1)}"] if p else []
    parts += [f"{v} video{'s' * (v != 1)}"] if v else []
    parts += [f"{x} video info file{'s' * (x != 1)} (.XML)"] if x else []
    return ", ".join(parts)


def item_folder(dest, it):
    """Day folder (relative) an item goes into."""
    folder = os.path.dirname(it["targets"][0])
    if os.path.basename(folder) == "Videos":
        folder = os.path.dirname(folder)
    return os.path.relpath(folder, dest)


def _mark(kind):
    if kind == "ok":
        return paint("✓" if FANCY else "OK", BOLD, GOOD)
    if kind == "warn":
        return paint("⚠" if FANCY else "!", BOLD, ATTN)
    return paint("✗" if FANCY else "x", BOLD, BAD)


def _row(name, value, width=19):
    print("    " + dim(name.ljust(width)) + value)


def _day(rel):
    head, day = os.path.split(rel)
    return dim(head + os.sep) + paint(day, BOLD), len(rel)


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
        print(f"  {_mark('bad')} Memory card    " + paint("not found", ATTN))
    if not info["dest"]:
        print(f"  {_mark('bad')} Backup folder  " + paint("not set (use --dest or SHOTLOFT_DEST)", ATTN))
        return
    if info["dest_drive"]:
        if info["dest_drive_connected"]:
            print(f"  {_mark('ok')} Backup drive   " + dest_path(info["dest_drive"]))
        else:
            print(f"  {_mark('bad')} Backup drive   " + dest_path(info["dest_drive"])
                  + paint("  not connected", ATTN))
    if info["dest_drive_connected"]:
        state = _mark("ok") if info["dest_exists"] else _mark("warn")
        note = "" if info["dest_exists"] else paint("  will be created", ATTN)
        print(f"  {state} Backup folder  " + dest_path(info["dest"]) + note)


def print_plan(plan):
    print("\n  " + paint("Backup folder", BOLD) + "  " + dest_path(plan["dest"])
          + dim(f"  {DOT} {plan['dest_existing_files']} files already there"))
    for s in plan["cards"]:
        print("\n  " + paint("Memory card", BOLD) + "    " + card_path(s["card"]))
        _row("On card", counts(s["photos_on_card"], s["videos_on_card"]) or "nothing")
        already = counts(s["already_photos"], s["already_videos"])
        _row("Already backed up", paint(already, BOLD, GOOD) if already else dim("nothing"))
        if s["new_photos"] or s["new_videos"] or s["new_xml"]:
            _row("New", paint(counts(s["new_photos"], s["new_videos"], s["new_xml"]), BOLD, ATTN)
                 + dim(f"  {DOT} {human(s['new_bytes'])}"))
            if s["repairs"]:
                n = s["repairs"]
                _row("", dim(f"incl. {n} file{'s' * (n != 1)} missing from an earlier backup, "
                             f"put back next to {'their' if n != 1 else 'its'} partner"))
            _row("Shot between", f"{nice_dt(s['from'])}  {dim(ARROW)}  {nice_dt(s['to'])}")
        else:
            _row("New", ok("nothing, all backed up"))
    days = {}
    for it in plan["items"]:  # items are already in capture order
        d = days.setdefault(item_folder(plan["dest"], it), [0, 0, 0])
        for i, n in enumerate(item_counts(it)):
            d[i] += n
    if days:
        print("\n  " + paint("Will be copied into", BOLD))
        print_days([(day, counts(*c)) for day, c in days.items()])
        print_space(plan)


def print_space(plan):
    where = drive_of(plan["dest"]) or plan["dest"]
    need, free = human(plan["needed_bytes"]), human(plan["free_bytes"])
    if plan["enough_space"]:
        print("\n  " + dim(f"Space: {need} needed {DOT} {free} free on {where}"))
    else:
        print("\n  " + bad(f"Not enough space: {need} needed, but only {free} is free on {where}."))
        print("  " + dim("Free up some space there, or choose another backup folder, then run ShotLoft again."))


def print_report(rep):
    print()
    took = f" in {nice_secs(rep['seconds'])}" if rep.get("seconds", 0) >= 1 else ""
    tot = [sum(c[k] for c in rep["by_day"].values()) for k in ("photos", "videos", "xml")]
    print("  " + ok(f"Copied {counts(*tot).replace(', ', ' and ') or 'nothing'}{took}"))
    if rep["by_day"]:
        print_days([(day, counts(c["photos"], c["videos"], c["xml"])) for day, c in rep["by_day"].items()])
    if rep["errors"]:
        print("\n  " + bad(f"{len(rep['errors'])} could not be copied:"))
        for e in rep["errors"]:
            print("    " + paint(os.path.basename(e["files"][0]), BAD) + dim(f"  {e['error']}"))
    if rep["raw_jpg_pairs"]:
        n = len(rep["raw_jpg_pairs"])
        print("\n  " + warn(f"{n} photo{'s were' if n != 1 else ' was'} shot as RAW + JPG"))
        rows = []
        for p in rep["raw_jpg_pairs"]:
            rel = os.path.relpath(p["arw"], rep["dest"])
            rows.append((os.path.dirname(rel), os.path.splitext(os.path.basename(rel))[0]
                         + dim("  .ARW + .JPG")))
        print_days(rows)


# ---------------------------------------------------------------- update notice

UPDATE_URL = os.environ.get("SHOTLOFT_UPDATE_URL",
                            "https://api.github.com/repos/imsoumya18/shotloft/releases/latest")
INSTALL_LINE = "curl -fsSL https://raw.githubusercontent.com/imsoumya18/shotloft/main/install.sh | bash"
INSTALL_LINE_WIN = "irm https://raw.githubusercontent.com/imsoumya18/shotloft/main/install.ps1 | iex"


def _vtuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", v or "")[:3])


def latest_version(timeout=3):
    """Latest released version on GitHub ("1.3.0"), or None when offline or unknown."""
    data = None
    try:
        import urllib.request
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": f"shotloft/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except Exception:
        # Some Python builds can't find the system's certificates; curl always can.
        if UPDATE_URL.startswith("https://") and shutil.which("curl"):
            try:
                data = subprocess.run(["curl", "-fsSL", "--max-time", str(timeout), UPDATE_URL],
                                      capture_output=True, timeout=timeout + 2).stdout
            except Exception:
                data = None
    try:
        return json.loads(data)["tag_name"].lstrip("vV")
    except Exception:
        return None


class UpdateCheck:
    """Looks for a newer release in the background, so the app never waits for the network."""

    def __init__(self):
        self.latest = None
        if os.environ.get("SHOTLOFT_NO_UPDATE_CHECK"):
            self.thread = None
            return
        import threading
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        self.latest = latest_version()

    def newer(self):
        if self.thread:
            self.thread.join(timeout=0.5)  # by the end of a run it has long finished
        return self.latest if self.latest and _vtuple(self.latest) > _vtuple(__version__) else None


def print_update(latest):
    print("\n  " + paint(f"A new version of ShotLoft is available: v{latest}", BOLD, ACCENT)
          + dim(f"  (you have v{__version__})"))
    print("  " + dim(f"To update, run this line in {'PowerShell' if IS_WIN else 'Terminal'}:"))
    print("  " + paint(INSTALL_LINE_WIN if IS_WIN else INSTALL_LINE, BOLD))


# ---------------------------------------------------------------- CLI

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
    """Saved settings. Settings from before the rename (Sony Import) are copied over once."""
    for path in (CONFIG_FILE, OLD_CONFIG_FILE):
        try:
            with open(path) as f:
                cfg = json.load(f)
        except Exception:
            continue
        if path == OLD_CONFIG_FILE:
            save_config(cfg)  # from now on ~/.shotloft.json is used
        return cfg
    return {}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"shotloft {__version__}")
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
    p = sub.add_parser("verify", help="check every card file byte by byte against the backup")
    p.add_argument("--dest", default=DEFAULT_DEST)
    p.add_argument("--card", action="append", help="card root; default: all detected")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("eject", help="safely eject memory cards (never formats)")
    p.add_argument("--card", action="append", help="card root; default: all detected")
    p = sub.add_parser("check-update", help="is a newer release available?")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("trash-jpgs", help="move JPGs that have an ARW twin to the Trash")
    p.add_argument("--report", required=True)
    args = ap.parse_args()

    if args.cmd is None:
        print("This is ShotLoft's engine. To back up a card, open the ShotLoft app from your\n"
              "Applications folder, Start menu or app menu. (See DEVELOPMENT.md.)")
        return 2
    if args.cmd == "detect":
        info = detect(args.dest)
        print(json.dumps(info, indent=2)) if args.json else print_detect(info)
        return 0
    if args.cmd == "eject":
        cards = args.card or detect()["cards"]
        if not cards:
            print("No Sony camera card found.", file=sys.stderr)
            return 2
        failed = 0
        for c in cards:
            done, details = eject(c)
            print(f"Ejected {c}" if done else f"Couldn't eject {c}: {details}")
            failed += not done
        return 1 if failed else 0
    if args.cmd == "check-update":
        latest = latest_version()
        newer = bool(latest) and _vtuple(latest) > _vtuple(__version__)
        if args.json:
            print(json.dumps({"current": __version__, "latest": latest, "update_available": newer}))
        elif latest is None:
            print(f"shotloft {__version__}: could not reach GitHub to check for updates.")
        elif newer:
            print_update(latest)
        else:
            print(f"shotloft {__version__} is up to date.")
        return 0
    if args.cmd == "trash-jpgs":
        with open(args.report) as f:
            rep = json.load(f)
        moved = trash([p["jpg"] for p in rep["raw_jpg_pairs"]])
        print(f"Moved {len(moved)} JPGs to the Trash.")
        return 0

    if not args.dest:
        print("No backup folder: pass --dest or set SHOTLOFT_DEST.", file=sys.stderr)
        return 2
    cards = args.card or detect()["cards"]
    for c in cards:
        if not is_sony_card(c):
            print(f"Not a Sony camera card: {c}", file=sys.stderr)
            return 2
    if not cards:
        print("No Sony camera card found.", file=sys.stderr)
        return 2
    if args.cmd == "verify":
        res = verify(os.path.abspath(args.dest), cards, quiet=args.json)
        print(json.dumps(res, indent=2)) if args.json else print_verify(res)
        return 0 if res["safe"] else 1
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
    if not plan["enough_space"]:
        print(f"Not enough space: {human(plan['needed_bytes'])} needed, "
              f"{human(plan['free_bytes'])} free in {plan['dest']}. Nothing was copied.", file=sys.stderr)
        return 3
    rep = run_import(plan)
    print_report(rep)
    if args.report:
        with open(args.report, "w") as f:
            json.dump(rep, f, indent=2)
        print(f"\nReport written to {args.report}")
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
