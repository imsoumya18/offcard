#!/usr/bin/env python3
"""offcard desktop app: a window on top of its engine (engine.py).

The window is a web page (ui/index.html) served by a small HTTP server on 127.0.0.1 that only
answers requests carrying a per-launch secret token. On macOS and Windows it opens in a native
window (pywebview, using the system's web view). Elsewhere, or if that fails, it opens in the
default browser and quits a little while after the page is closed.

  python3 offcard.py              open the app
  python3 offcard.py --browser    always use the browser
  python3 offcard.py --serve      no window or browser; print the URL (tests)
"""
import http.server
import importlib.util
import json
import os
import secrets
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

# The engine (engine.py) and HDR merge (hdr.py) are loaded at run time, so the app bundler can't
# see what they import. Importing those modules here makes sure they are packed into the built app.
import argparse, base64, ctypes, datetime, getpass, hashlib, io, re, string, struct, urllib.request, zlib  # noqa: E401,F401
try:
    import numpy, rawpy, PIL.Image, PIL.ImageFilter, PIL.TiffImagePlugin  # noqa: E401,F401
except ImportError:
    pass  # running from source without them: HDR merge says what to install

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
for _name in ("stdout", "stderr"):  # windowed builds have no console
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w"))


def _load_engine():
    spec = importlib.util.spec_from_file_location("offcard_engine", os.path.join(HERE, "engine.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load_engine()
HDR, HDR_MISSING = None, None
try:
    _spec = importlib.util.spec_from_file_location("offcard_hdr", os.path.join(HERE, "hdr.py"))
    HDR = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(HDR)
    import rawpy, PIL.Image  # noqa: E401,F401
except ImportError as _e:
    HDR, HDR_MISSING = None, f"HDR merge needs NumPy, rawpy and Pillow ({_e.name} is missing): pip install numpy rawpy pillow"
TOKEN = secrets.token_urlsafe(24)
WINDOW = None  # the pywebview window, when there is one


# ---------------------------------------------------------------- state

class App:
    def __init__(self):
        self.lock = threading.Lock()
        self.dest = E.load_config().get("dest")
        self.job = None          # {"kind", "state": running|done|error, "progress", "result", "error"}
        self.hdr_job = None      # the same, for HDR Merge (scan or merge), which runs alongside a backup
        self.hdr_folder = E.load_config().get("hdr_folder")
        self.hdr_sets = None     # the last scan's bracket sets (engine.find_brackets)
        self.thumbs = {}         # path -> (mtime, data URI)
        self.plan_key = None     # [cards, dest] the last plan was made for, so the page needn't redo it
        self.plan = None         # last build_plan() result, used by "import"
        self.tags = {}           # day tags set for this backup: {"24Oct26": "Goa" or "" for none}
        self.report = None       # last run_import() result, used by "trash"
        self.last_seen = time.time()
        self.update = E.UpdateCheck()
        self.cards_override = [c for c in os.environ.get("OFFCARD_TEST_CARDS", "").split(os.pathsep) if c]

    def cards(self):
        if self.cards_override:
            return [c for c in self.cards_override if E.is_sony_card(c)]
        return E.detect()["cards"]

    # -- background jobs
    def start(self, kind, fn):
        with self.lock:
            if self.job and self.job["state"] == "running":
                raise RuntimeError("Something is already running. Wait for it to finish.")
            self.job = {"kind": kind, "state": "running", "progress": None, "result": None, "error": None}
        job = self.job

        def hook(label, done, total, files_done, files_total, nbytes, elapsed):
            job["progress"] = {"label": label, "done": done, "total": total, "files_done": files_done,
                               "files_total": files_total, "bytes": nbytes, "elapsed": round(elapsed, 1)}

        def run():
            E.PROGRESS_HOOK = hook
            try:
                job["result"] = fn()
                job["state"] = "done"
            except Exception as e:
                job["error"] = str(e)
                job["state"] = "error"
            finally:
                E.PROGRESS_HOOK = None

        threading.Thread(target=run, daemon=True).start()
        return {"started": kind}


    def start_hdr(self, kind, fn):
        with self.lock:
            if self.hdr_job and self.hdr_job["state"] == "running":
                raise RuntimeError("HDR Merge is busy. Wait for it to finish.")
            self.hdr_job = {"kind": kind, "state": "running", "progress": None, "result": None, "error": None,
                            "id": time.time()}
        job = self.hdr_job

        def run():
            try:
                job["result"] = fn(job)
                job["state"] = "done"
            except Exception as e:
                job["error"] = str(e)
                job["state"] = "error"

        threading.Thread(target=run, daemon=True).start()
        return {"started": kind}


APP = App()


def card_summary(card):
    items = E.scan_card(card)
    photos = sum(len(it["files"]) for it in items if it["kind"] != "video")
    videos = sum(1 for it in items if it["kind"] == "video")
    return {"path": card, "name": os.path.basename(card.rstrip("/\\")) or card,
            "photos": photos, "videos": videos}


def day_summary(rel, d):
    name = os.path.basename(rel)
    m = E.DAY_RE.match(name)
    key, tag = (m.group(1), m.group(2) or "") if m else (name, "")
    return {"folder": rel, "key": key, "tag": tag, "label": day_label(os.path.join(os.path.dirname(rel), key)),
            "photos": d["photos"], "videos": d["videos"], "xml": d["xml"], "bytes": d["bytes"], "ids": d["ids"],
            "new": not os.path.isdir(os.path.join(APP.dest or "", os.path.dirname(rel), name))}


def day_label(rel):
    """'2026/10. October/17Oct26' -> '17 Oct 2026'."""
    day = os.path.basename(rel)
    return f"{int(day[:2])} {day[2:5]} 20{day[5:7]}" if len(day) == 7 and day[:2].isdigit() else day


def folder_tree(dest, items):
    """The folders a backup writes into, as a tree under the backup folder, in shooting order:
    each with whether it's new (doesn't exist yet) and how many files go straight into it."""
    counts = {}
    for it in items:
        for target in it["targets"]:
            rel = os.path.relpath(os.path.dirname(target), dest)
            counts[rel] = counts.get(rel, 0) + 1
    root = {"name": os.path.basename(dest.rstrip("/\\")) or dest, "new": not os.path.isdir(dest),
            "files": 0, "children": []}
    for rel, n in counts.items():
        node, path = root, dest
        for part in ([] if rel == "." else rel.split(os.sep)):
            path = os.path.join(path, part)
            child = next((c for c in node["children"] if c["name"] == part), None)
            if child is None:
                child = {"name": part, "new": not os.path.isdir(path), "files": 0, "children": []}
                node["children"].append(child)
            node = child
        node["files"] += n
    return root


def plan_summary(plan):
    """What the backup will do, with each day's folder named for its tag (set now, or already in
    the backup) and the files that go into it."""
    items, renames = E.apply_tags(plan, APP.tags)
    days = {}
    for i, it in enumerate(items):
        d = days.setdefault(E.item_folder(plan["dest"], it),
                            {"photos": 0, "videos": 0, "xml": 0, "bytes": 0, "ids": []})
        for k, n in zip(("photos", "videos", "xml"), E.item_counts(it)):
            d[k] += n
        d["bytes"] += it["size"]
        d["ids"].append(i)
    cards = plan["cards"]
    total = lambda k: sum(c[k] for c in cards)
    return {
        "new_photos": total("new_photos"), "new_videos": total("new_videos"), "new_xml": total("new_xml"),
        "repairs": total("repairs"), "already_photos": total("already_photos"),
        "already_videos": total("already_videos"), "new_files": sum(len(it["files"]) for it in plan["items"]),
        "needed_bytes": plan["needed_bytes"], "free_bytes": plan["free_bytes"],
        "enough_space": plan["enough_space"], "dest_existing_files": plan["dest_existing_files"],
        "days": [day_summary(k, v) for k, v in days.items()],
        "renames": [os.path.relpath(new, plan["dest"]) for new in renames.values()],
        "tree": folder_tree(plan["dest"], items),
        "from": min((c["from"] for c in cards if c["from"]), default=None),
        "to": max((c["to"] for c in cards if c["to"]), default=None),
    }


def report_summary(rep):
    tot = {k: sum(d[k] for d in rep["by_day"].values()) for k in ("photos", "videos", "xml")}
    return {**tot, "files": len(rep["copied"]), "seconds": rep["seconds"],
            "errors": [{"file": os.path.basename(e["files"][0]), "error": e["error"]} for e in rep["errors"]],
            "raw_jpg_pairs": len(rep["raw_jpg_pairs"]), "days": list(rep["by_day"])}


# ---------------------------------------------------------------- folder picker

def pick_folder(start=None, title="Choose your backup folder"):
    """Native 'choose folder' dialog. Returns a path, or None if cancelled."""
    if WINDOW is not None:
        import webview
        res = WINDOW.create_file_dialog(webview.FOLDER_DIALOG, directory=start or "")
        return res[0] if res else None
    try:
        if E.IS_MAC:
            r = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{title}")'],
                               capture_output=True, text=True)
            return r.stdout.strip().rstrip("/") or None
        if E.IS_WIN:
            ps = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                  f"$d.Description = '{title}'; if ($d.ShowDialog() -eq 'OK') {{ $d.SelectedPath }}")
            r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, text=True)
            return r.stdout.strip() or None
        for cmd in (["zenity", "--file-selection", "--directory", f"--title={title}"],
                    ["kdialog", "--getexistingdirectory", start or os.path.expanduser("~")]):
            if shutil.which(cmd[0]):
                r = subprocess.run(cmd, capture_output=True, text=True)
                return r.stdout.strip() or None
    except Exception:
        pass
    raise RuntimeError("No folder picker is available here. Type or paste the folder path instead.")


# ---------------------------------------------------------------- API

def api_state(_):
    APP.last_seen = time.time()
    info = E.detect(APP.dest)
    cards = APP.cards()
    newer = APP.update.newer()
    return {
        "version": E.__version__, "trash_name": E.TRASH, "file_manager": E.FILE_MANAGER,
        "cards": [card_summary(c) for c in cards],
        "dest": APP.dest, "dest_drive": info["dest_drive"],
        "dest_drive_connected": info["dest_drive_connected"], "dest_exists": info["dest_exists"],
        "free_bytes": E.free_bytes(APP.dest) if APP.dest and info["dest_drive_connected"] else None,
        "job": APP.job, "hdr_job": hdr_job_brief(), "hdr_missing": HDR_MISSING, "hdr_folder": APP.hdr_folder,
        "hdr_folder_exists": bool(APP.hdr_folder and os.path.isdir(APP.hdr_folder)),
        "hdr_new": None if APP.hdr_sets is None else sum(not st["done"] for st in APP.hdr_sets), "update": {"latest": newer, "line": E.INSTALL_LINE_WIN if E.IS_WIN else E.INSTALL_LINE}
                                  if newer else None,
        "can_pick": True, "plan_for": APP.plan_key, "recent_dests": recent_dests(),
        "recent_tags": E.load_config().get("recent_tags", []),
    }


def api_set_dest(body):
    path = E.clean_path(body.get("path") or "")
    if not path:
        raise RuntimeError("Choose a folder first.")
    if os.path.exists(path) and not os.path.isdir(path):
        raise RuntimeError("That's a file, not a folder.")
    APP.dest, APP.plan = path, None
    cfg = E.load_config()
    recent = [path] + [p for p in cfg.get("recent_dests", []) if p != path]
    E.save_config({**cfg, "dest": path, "recent_dests": recent[:5]})
    return {"dest": path}


def recent_dests():
    """Backup folders used before (newest first, current one included), for choosing each time."""
    cfg = E.load_config()
    seen = []
    for p in [APP.dest] + cfg.get("recent_dests", []):
        if p and p not in seen:
            seen.append(p)
    return seen[:5]


def api_pick(_):
    path = pick_folder(APP.dest)
    return api_set_dest({"path": path}) if path else {"dest": APP.dest, "cancelled": True}


def _need_ready():
    cards = APP.cards()
    if not cards:
        raise RuntimeError("Put a memory card in first.")
    if not APP.dest:
        raise RuntimeError("Choose a backup folder first.")
    drive = E.drive_of(APP.dest)
    if drive and not os.path.isdir(drive):
        raise RuntimeError(f"The backup drive {drive} isn't connected.")
    return cards


def api_plan(_):
    cards = _need_ready()
    dest = APP.dest
    APP.plan_key = [sorted(cards), dest]

    def run():
        APP.plan = E.build_plan(os.path.abspath(dest), cards)
        return plan_summary(APP.plan)
    return APP.start("plan", run)


def api_import(body):
    """Back up everything, or only the chosen files ({"ids": [...]} from the plan's days)."""
    if not APP.plan or not APP.plan["items"]:
        raise RuntimeError("Nothing to back up.")
    plan = APP.plan
    ids = (body or {}).get("ids")
    if ids is not None:
        plan = E.choose(plan, [i for i in ids if isinstance(i, int)])
        if not plan["items"]:
            raise RuntimeError("Choose at least one file to back up.")
    if not plan["enough_space"]:
        raise RuntimeError("There isn't enough space on the backup drive.")
    plan = dict(plan, tags=dict(APP.tags))

    def run():
        rep = E.run_import(plan)  # renames tagged day folders, then copies; never an empty folder
        APP.report, APP.plan, APP.tags = rep, None, {}
        return report_summary(rep)
    return APP.start("import", run)


def api_tag(body):
    """Tag one day of this backup: {"day": "24Oct26", "tag": "Goa"}; an empty tag removes it."""
    if not APP.plan:
        raise RuntimeError("Check the card first.")
    day, tag = str(body.get("day") or ""), E.clean_tag(str(body.get("tag") or ""))
    if not E.DAY_RE.match(day) or E.DAY_RE.match(day).group(2):
        raise RuntimeError("That isn't a day.")
    APP.tags[day] = tag
    if tag:
        cfg = E.load_config()
        recent = [tag] + [t for t in cfg.get("recent_tags", []) if t.lower() != tag.lower()]
        E.save_config({**cfg, "recent_tags": recent[:8]})
    summary = plan_summary(APP.plan)
    if APP.job and APP.job["kind"] == "plan" and APP.job["state"] == "done":
        APP.job["result"] = summary
    return summary


def api_plan_items(_):
    """Every file the plan would copy, by day, for choosing: what it is, when, and how big."""
    if not APP.plan:
        raise RuntimeError("Check the card first.")
    out = []
    for i, it in enumerate(APP.plan["items"]):
        names = [os.path.basename(f) for f in it["files"]]
        kind = "video" if it["kind"] == "video" else "pair" if it["kind"] == "pair" and len(names) > 1 else "photo"
        out.append({"id": i, "day": E.day_key(it["dt"]), "kind": kind, "name": os.path.basename(it["key_file"]),
                    "names": names, "time": it["dt"][11:19], "size": it["size"], "repair": bool(it.get("repair"))})
    return {"items": out}


def api_plan_thumbs(body):
    """Small previews of the chosen plan files' photos, from the camera's own embedded JPEG."""
    if not APP.plan:
        raise RuntimeError("Check the card first.")
    items, out = APP.plan["items"], {}
    for i in body.get("ids") or []:
        if not isinstance(i, int) or not 0 <= i < len(items) or items[i]["kind"] == "video":
            continue
        try:
            out[str(i)] = thumbnail(items[i]["key_file"], 200)
        except Exception:
            out[str(i)] = None
    return {"thumbs": out}


def api_verify(_):
    cards = _need_ready()
    dest = APP.dest

    def run():
        res = E.verify(os.path.abspath(dest), cards, quiet=True)
        return {"safe": res["safe"], "seconds": res["seconds"], "cards": [
            {"card": st["card"], "files": st["files"], "verified": st["verified"],
             "missing": [os.path.basename(f) for f in st["missing"]],
             "different": [os.path.basename(f) for f in st["different"]],
             "trashed_jpg": len(st["trashed_jpg"])} for st in res["cards"]]}
    return APP.start("verify", run)


def api_eject(_):
    results = []
    for c in APP.cards():
        done, details = E.eject(c)
        results.append({"card": c, "ejected": done, "details": details})
    APP.plan = None
    return {"results": results}


def api_trash(_):
    if not APP.report or not APP.report["raw_jpg_pairs"]:
        raise RuntimeError("There are no extra JPGs to move.")
    moved = E.trash([p["jpg"] for p in APP.report["raw_jpg_pairs"]])
    APP.report["raw_jpg_pairs"] = []
    return {"moved": len(moved)}


# ---------------------------------------------------------------- HDR Merge

def thumbnail(path, size=240):
    """Small JPEG data URI: the RAW's embedded preview, or the merged JPEG itself. Cached by file,
    size and modification time; a file without a usable preview is remembered as None."""
    mtime = os.path.getmtime(path)
    hit = APP.thumbs.get((path, size))
    if hit and hit[0] == mtime:
        return hit[1]
    uri = None
    try:
        from PIL import Image
        turn = 0
        if path.upper().endswith(".ARW"):
            with rawpy.imread(path) as r:
                th = r.extract_thumb()
                turn = {3: 180, 5: 90, 6: -90}.get(r.sizes.flip, 0)   # the camera's preview isn't turned
            im = Image.open(io.BytesIO(th.data)) if th.format == rawpy.ThumbFormat.JPEG else None
        else:
            im = Image.open(path)
        if im is not None:
            im.draft("RGB", (size, size))
            im = im.convert("RGB")
            if turn:
                im = im.rotate(turn, expand=True)
            im.thumbnail((size, size))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        uri = None
    APP.thumbs[(path, size)] = (mtime, uri)
    return uri


def set_thumb(st):
    if HDR is None:
        return None
    mid = min(range(len(st["files"])), key=lambda k: abs(st["biases"][k]))
    try:
        return thumbnail(st["output"] if st["done"] else st["files"][mid])
    except Exception:
        return None


def set_summary(i, st):
    rel = os.path.relpath(st["folder"], APP.hdr_folder)
    d = datetime.datetime.strptime(st["taken"][:19], "%Y:%m:%d %H:%M:%S")
    return {"id": i, "folder": "" if rel == "." else rel, "names": st["names"], "biases": st["biases"],
            "date": f"{d.day} {d:%b %Y}", "time": f"{d:%H:%M}", "output": os.path.basename(st["output"]),
            "done": st["done"], "thumb": st.get("thumb")}


def hdr_job_brief():
    """The HDR job for /api/state, without the sets and previews (the page gets those once from
    /api/hdr/sets), so polling stays small."""
    j = APP.hdr_job
    if not j:
        return None
    brief = {k: v for k, v in j.items() if k != "result"}
    r = j["result"] or {}
    brief["result"] = {"sets": len(r.get("sets", [])), "merged": len(r.get("merged", [])),
                       "failed": r.get("failed", [])} if j["result"] is not None else None
    return brief


def api_hdr_sets(_):
    return {"folder": APP.hdr_folder,
            "sets": None if APP.hdr_sets is None else [set_summary(i, st) for i, st in enumerate(APP.hdr_sets)]}


def api_hdr_folder(body):
    path = E.clean_path(body.get("path") or "")
    if not path:
        raise RuntimeError("Choose a folder first.")
    if not os.path.isdir(path):
        raise RuntimeError("That folder doesn't exist.")
    if E.card_root(path):
        raise RuntimeError("That folder is on a memory card, and offcard never writes to a card. "
                           "Back the card up first (Card Backup), then merge from the backup.")
    APP.hdr_folder, APP.hdr_sets = path, None
    E.save_config({**E.load_config(), "hdr_folder": path})
    return {"hdr_folder": path}


def api_hdr_pick(_):
    path = pick_folder(APP.hdr_folder or APP.dest, "Choose a folder with bracketed shots")
    return api_hdr_folder({"path": path}) if path else {"hdr_folder": APP.hdr_folder, "cancelled": True}


def api_hdr_scan(_):
    folder = APP.hdr_folder
    if not folder or not os.path.isdir(folder):
        raise RuntimeError("Choose a folder first.")

    def run(job):
        def prog(done, total):
            job["progress"] = {"done": done, "total": total, "stage": "Reading photos"}
        sets = E.find_brackets(folder, prog)
        for n, st in enumerate(sets):
            job["progress"] = {"done": n, "total": len(sets), "stage": "Making previews"}
            st["thumb"] = set_thumb(st)
        APP.hdr_sets = sets
        return {"sets": sets}
    return APP.start_hdr("scan", run)


def api_hdr_merge(body):
    if HDR is None:
        raise RuntimeError(HDR_MISSING)
    sets = APP.hdr_sets or []
    ids = body.get("ids") or []
    chosen = [(i, sets[i]) for i in ids if isinstance(i, int) and 0 <= i < len(sets)]
    if not chosen:
        raise RuntimeError("Choose at least one set to merge.")
    tiff = bool(body.get("tiff"))

    def run(job):
        done, failed = [], []
        for n, (i, st) in enumerate(chosen):
            name = os.path.basename(st["output"])

            def prog(frac, stage, n=n, name=name):
                job["progress"] = {"done": n + frac, "total": len(chosen), "name": name, "stage": stage}
            prog(0, "Reading")
            try:
                HDR.merge_set(st["files"], st["output"], tiff=tiff, progress=prog)
                st["done"] = True
                st["thumb"] = set_thumb(st)
                done.append(i)
            except Exception as e:
                failed.append({"file": name, "error": str(e)})
        return {"merged": done, "failed": failed, "sets": sets}
    return APP.start_hdr("merge", run)


def api_reveal(body):
    """Open a merged set's HDR folder in Finder / File Explorer / the file manager."""
    sets = APP.hdr_sets or []
    i = body.get("id")
    if not isinstance(i, int) or not 0 <= i < len(sets):
        raise RuntimeError("Choose a set first.")
    path = os.path.dirname(sets[i]["output"])
    if not os.path.isdir(path):
        raise RuntimeError("That set hasn't been merged yet.")
    if E.IS_MAC:
        subprocess.Popen(["open", path])
    elif E.IS_WIN:
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
    return {"opened": path}


# ---------------------------------------------------------------- card watcher (Mac app)

def watch_cards():
    """With --agent (the Mac menu bar app's engine): when a card goes in, check what's new on it
    straight away, so the app can tell the user and show it the moment they open the panel."""
    seen = set()
    while True:
        time.sleep(2)
        try:
            cards = APP.cards()
            new = set(cards) - seen
            seen = set(cards)
            busy = APP.job and APP.job["state"] == "running"
            drive = E.drive_of(APP.dest) if APP.dest else None   # None: on the internal disk, always there
            if new and not busy and APP.dest and (drive is None or os.path.isdir(drive)):
                api_plan({})
        except Exception:
            pass


def api_reset(_):
    with APP.lock:
        if APP.job and APP.job["state"] == "running":
            raise RuntimeError("Something is still running.")
        APP.job, APP.plan, APP.tags = None, None, {}
    return {"ok": True}


ROUTES = {"/api/state": api_state, "/api/dest": api_set_dest, "/api/pick": api_pick, "/api/plan": api_plan,
          "/api/import": api_import, "/api/verify": api_verify, "/api/eject": api_eject,
          "/api/trash": api_trash, "/api/reset": api_reset, "/api/hdr/folder": api_hdr_folder,
          "/api/hdr/pick": api_hdr_pick, "/api/hdr/scan": api_hdr_scan, "/api/hdr/merge": api_hdr_merge,
          "/api/hdr/sets": api_hdr_sets, "/api/reveal": api_reveal, "/api/tag": api_tag,
          "/api/plan/items": api_plan_items, "/api/plan/thumbs": api_plan_thumbs}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self):
        host = self.headers.get("Host", "")
        return host == f"127.0.0.1:{self.server.server_address[1]}"  # blocks DNS-rebinding tricks

    def do_GET(self):
        if not self._allowed():
            return self._send(403, {"error": "forbidden"})
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            if urllib.parse.parse_qs(url.query).get("t", [""])[0] != TOKEN:
                return self._send(403, b"Open offcard from its app icon.", "text/plain")
            with open(os.path.join(HERE, "ui", "index.html"), "rb") as f:
                page = f.read().replace(b"__TOKEN__", TOKEN.encode())
            return self._send(200, page, "text/html; charset=utf-8")
        if url.path == "/icon.png":
            with open(os.path.join(HERE, "docs", "icon.png"), "rb") as f:
                return self._send(200, f.read(), "image/png")
        self._dispatch(url.path, {})

    def do_POST(self):
        if not self._allowed():
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        self._dispatch(urllib.parse.urlparse(self.path).path, body)

    def _dispatch(self, path, body):
        if self.headers.get("X-Token") != TOKEN:
            return self._send(403, {"error": "forbidden"})
        fn = ROUTES.get(path)
        if not fn:
            return self._send(404, {"error": "not found"})
        try:
            self._send(200, fn(body))
        except Exception as e:
            self._send(400, {"error": str(e)})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main():
    mode = "window"
    if "--browser" in sys.argv or os.environ.get("OFFCARD_BROWSER"):
        mode = "browser"
    if "--serve" in sys.argv:
        mode = "serve"
    if "--version" in sys.argv:
        print(f"offcard {E.__version__}")
        return 0
    if "--hdr-selftest" in sys.argv:  # checks that the built app can merge (tests; result also to a file)
        problems = [HDR_MISSING] if HDR is None else HDR.selftest()[0]
        out = "\n".join(problems) or "PASS"
        print(out, flush=True)
        if os.environ.get("OFFCARD_URL_FILE"):  # windowed builds have no console to print to
            with open(os.environ["OFFCARD_URL_FILE"], "w") as f:
                f.write(out)
        return 1 if problems else 0
    server = Server(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={TOKEN}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if mode == "serve":
        if "--agent" in sys.argv:  # the Mac menu bar app's engine: watch cards, and go when the app goes
            threading.Thread(target=watch_cards, daemon=True).start()
            parent = os.getppid()

            def follow_parent():
                while os.getppid() == parent:
                    time.sleep(2)
                os._exit(0)
            threading.Thread(target=follow_parent, daemon=True).start()
        info = json.dumps({"url": url, "token": TOKEN})
        print(info, flush=True)
        if os.environ.get("OFFCARD_URL_FILE"):  # windowed builds have no console to print to
            with open(os.environ["OFFCARD_URL_FILE"], "w") as f:
                f.write(info)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    if mode == "window" and not (sys.platform.startswith("linux")):
        try:
            import webview
            global WINDOW
            WINDOW = webview.create_window("offcard", url, width=760, height=640, min_size=(620, 520))
            webview.start()
            return 0
        except Exception:
            pass  # no native web view here: fall back to the browser

    webbrowser.open(url)
    print(f"offcard is open in your browser: {url}\nClose the page to quit.", flush=True)
    while time.time() - APP.last_seen < 45 or (APP.job and APP.job["state"] == "running"):
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
