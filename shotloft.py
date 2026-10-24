#!/usr/bin/env python3
"""ShotLoft desktop app: a window on top of its engine (engine.py).

The window is a web page (ui/index.html) served by a small HTTP server on 127.0.0.1 that only
answers requests carrying a per-launch secret token. On macOS and Windows it opens in a native
window (pywebview, using the system's web view). Elsewhere, or if that fails, it opens in the
default browser and quits a little while after the page is closed.

  python3 shotloft.py              open the app
  python3 shotloft.py --browser    always use the browser
  python3 shotloft.py --serve      no window or browser; print the URL (tests)
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

# The engine (engine.py) is loaded at run time, so the app bundler can't see what it imports.
# Importing those modules here makes sure they are packed into the built app.
import argparse, ctypes, datetime, getpass, hashlib, re, string, struct, urllib.request  # noqa: E401,F401

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
for _name in ("stdout", "stderr"):  # windowed builds have no console
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w"))


def _load_engine():
    spec = importlib.util.spec_from_file_location("shotloft_engine", os.path.join(HERE, "engine.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load_engine()
TOKEN = secrets.token_urlsafe(24)
WINDOW = None  # the pywebview window, when there is one


# ---------------------------------------------------------------- state

class App:
    def __init__(self):
        self.lock = threading.Lock()
        self.dest = E.load_config().get("dest")
        self.job = None          # {"kind", "state": running|done|error, "progress", "result", "error"}
        self.plan = None         # last build_plan() result, used by "import"
        self.report = None       # last run_import() result, used by "trash"
        self.last_seen = time.time()
        self.update = E.UpdateCheck()
        self.cards_override = [c for c in os.environ.get("SHOTLOFT_TEST_CARDS", "").split(os.pathsep) if c]

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


APP = App()


def card_summary(card):
    items = E.scan_card(card)
    photos = sum(len(it["files"]) for it in items if it["kind"] != "video")
    videos = sum(1 for it in items if it["kind"] == "video")
    return {"path": card, "name": os.path.basename(card.rstrip("/\\")) or card,
            "photos": photos, "videos": videos}


def day_label(rel):
    """'2026/10. October/17Oct26' -> '17 Oct 2026'."""
    day = os.path.basename(rel)
    return f"{int(day[:2])} {day[2:5]} 20{day[5:7]}" if len(day) == 7 and day[:2].isdigit() else day


def plan_summary(plan):
    days = {}
    for it in plan["items"]:
        d = days.setdefault(E.item_folder(plan["dest"], it), [0, 0, 0])
        for i, n in enumerate(E.item_counts(it)):
            d[i] += n
    cards = plan["cards"]
    total = lambda k: sum(c[k] for c in cards)
    return {
        "new_photos": total("new_photos"), "new_videos": total("new_videos"), "new_xml": total("new_xml"),
        "repairs": total("repairs"), "already_photos": total("already_photos"),
        "already_videos": total("already_videos"), "new_files": sum(len(it["files"]) for it in plan["items"]),
        "needed_bytes": plan["needed_bytes"], "free_bytes": plan["free_bytes"],
        "enough_space": plan["enough_space"], "dest_existing_files": plan["dest_existing_files"],
        "days": [{"folder": k, "label": day_label(k), "photos": v[0], "videos": v[1], "xml": v[2]}
                 for k, v in days.items()],
        "from": min((c["from"] for c in cards if c["from"]), default=None),
        "to": max((c["to"] for c in cards if c["to"]), default=None),
    }


def report_summary(rep):
    tot = {k: sum(d[k] for d in rep["by_day"].values()) for k in ("photos", "videos", "xml")}
    return {**tot, "files": len(rep["copied"]), "seconds": rep["seconds"],
            "errors": [{"file": os.path.basename(e["files"][0]), "error": e["error"]} for e in rep["errors"]],
            "raw_jpg_pairs": len(rep["raw_jpg_pairs"])}


# ---------------------------------------------------------------- folder picker

def pick_folder(start=None):
    """Native 'choose folder' dialog. Returns a path, or None if cancelled."""
    if WINDOW is not None:
        import webview
        res = WINDOW.create_file_dialog(webview.FOLDER_DIALOG, directory=start or "")
        return res[0] if res else None
    try:
        if E.IS_MAC:
            r = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "Choose your backup folder")'],
                               capture_output=True, text=True)
            return r.stdout.strip().rstrip("/") or None
        if E.IS_WIN:
            ps = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                  "$d.Description = 'Choose your backup folder'; if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }")
            r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, text=True)
            return r.stdout.strip() or None
        for cmd in (["zenity", "--file-selection", "--directory", "--title=Choose your backup folder"],
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
        "job": APP.job, "update": {"latest": newer, "line": E.INSTALL_LINE_WIN if E.IS_WIN else E.INSTALL_LINE}
                                  if newer else None,
        "can_pick": True,
    }


def api_set_dest(body):
    path = E.clean_path(body.get("path") or "")
    if not path:
        raise RuntimeError("Choose a folder first.")
    if os.path.exists(path) and not os.path.isdir(path):
        raise RuntimeError("That's a file, not a folder.")
    APP.dest, APP.plan = path, None
    E.save_config({**E.load_config(), "dest": path})
    return {"dest": path}


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

    def run():
        APP.plan = E.build_plan(os.path.abspath(dest), cards)
        return plan_summary(APP.plan)
    return APP.start("plan", run)


def api_import(_):
    if not APP.plan or not APP.plan["items"]:
        raise RuntimeError("Nothing to back up.")
    if not APP.plan["enough_space"]:
        raise RuntimeError("There isn't enough space on the backup drive.")
    plan = APP.plan

    def run():
        os.makedirs(plan["dest"], exist_ok=True)
        rep = E.run_import(plan)
        APP.report, APP.plan = rep, None
        return report_summary(rep)
    return APP.start("import", run)


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


def api_reset(_):
    with APP.lock:
        if APP.job and APP.job["state"] == "running":
            raise RuntimeError("Something is still running.")
        APP.job, APP.plan = None, None
    return {"ok": True}


ROUTES = {"/api/state": api_state, "/api/dest": api_set_dest, "/api/pick": api_pick, "/api/plan": api_plan,
          "/api/import": api_import, "/api/verify": api_verify, "/api/eject": api_eject,
          "/api/trash": api_trash, "/api/reset": api_reset}


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
                return self._send(403, b"Open ShotLoft from its app icon.", "text/plain")
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
    if "--browser" in sys.argv or os.environ.get("SHOTLOFT_BROWSER"):
        mode = "browser"
    if "--serve" in sys.argv:
        mode = "serve"
    if "--version" in sys.argv:
        print(f"shotloft {E.__version__}")
        return 0
    server = Server(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={TOKEN}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if mode == "serve":
        info = json.dumps({"url": url, "token": TOKEN})
        print(info, flush=True)
        if os.environ.get("SHOTLOFT_URL_FILE"):  # windowed builds have no console to print to
            with open(os.environ["SHOTLOFT_URL_FILE"], "w") as f:
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
            WINDOW = webview.create_window("ShotLoft", url, width=760, height=640, min_size=(620, 520))
            webview.start()
            return 0
        except Exception:
            pass  # no native web view here: fall back to the browser

    webbrowser.open(url)
    print(f"ShotLoft is open in your browser: {url}\nClose the page to quit.", flush=True)
    while time.time() - APP.last_seen < 45 or (APP.job and APP.job["state"] == "running"):
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
