#!/usr/bin/env python3
"""End-to-end test of the desktop app's backend, the way its page uses it.

Usage:  python tests/app_test.py <command to run the app...>
  e.g.  python tests/app_test.py python shotloft.py
        python tests/app_test.py "dist/ShotLoft.app/Contents/MacOS/ShotLoft"

HDR merge needs NumPy, rawpy and Pillow wherever the app runs (the built app bundles them).
"""
import http.client, json, os, subprocess, sys, tempfile, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_test import make_card, make_bracket_day, EXPECTED, tree  # noqa: E402


def main():
    tool = sys.argv[1:]
    if not tool:
        sys.exit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        card, dest, home = (os.path.join(tmp, n) for n in ("card", "backup", "home"))
        os.makedirs(home)
        make_card(card)
        urlfile = os.path.join(tmp, "url.json")
        env = {**os.environ, "HOME": home, "USERPROFILE": home, "SHOTLOFT_NO_UPDATE_CHECK": "1",
               "SHOTLOFT_TEST_CARDS": card, "SHOTLOFT_URL_FILE": urlfile}
        proc = subprocess.Popen(tool + ["--serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(600):
                if os.path.exists(urlfile) and os.path.getsize(urlfile):
                    break
                if proc.poll() is not None:
                    sys.exit(f"FAIL: app exited early with code {proc.returncode}")
                time.sleep(0.1)
            else:
                sys.exit("FAIL: app never started")
            info = json.load(open(urlfile))
            u = urllib.parse.urlparse(info["url"])
            host, token = u.netloc, info["token"]

            def call(path, body=None, tok=token, hdr_host=host):
                c = http.client.HTTPConnection(host, timeout=30)
                c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None,
                          {"X-Token": tok, "Host": hdr_host, "Content-Type": "application/json"})
                r = c.getresponse()
                return r.status, (json.loads(r.read() or b"{}") if path.startswith("/api") else r.read())

            def wait(kind, key="job"):
                for _ in range(600):
                    st, s = call("/api/state")
                    j = s[key]
                    if j and j["kind"] == kind and j["state"] != "running":
                        if j["state"] == "error":
                            sys.exit(f"FAIL: {kind}: {j['error']}")
                        return j["result"]
                    time.sleep(0.1)
                sys.exit(f"FAIL: {kind} never finished")

            # Security: no token, wrong token, or a foreign Host header are all refused.
            assert call("/api/state", tok="")[0] == 403, "no token"
            assert call("/api/state", tok="wrong")[0] == 403, "wrong token"
            assert call("/api/state", hdr_host="evil.example:80")[0] == 403, "foreign host"
            assert call("/?t=wrong")[0] == 403 and call(f"/?t={token}")[0] == 200, "page token"

            st, s = call("/api/state")
            assert st == 200 and s["cards"] and s["cards"][0]["photos"] == 5 and s["dest"] is None, s
            assert call("/api/dest", {"path": dest})[0] == 200
            call("/api/plan", {})
            plan = wait("plan")
            assert plan["new_photos"] == 5 and plan["new_videos"] == 1 and plan["enough_space"], plan
            call("/api/import", {})
            rep = wait("import")
            assert rep["photos"] == 5 and rep["videos"] == 1 and not rep["errors"] and rep["raw_jpg_pairs"] == 1, rep
            got = tree(dest)
            assert got == EXPECTED, f"backup tree: missing {EXPECTED - got}, extra {got - EXPECTED}"
            call("/api/verify", {})
            ver = wait("verify")
            assert ver["safe"] and ver["cards"][0]["verified"] == 7, ver
            st, ej = call("/api/eject", {})  # the test card is a folder, so eject must refuse
            assert st == 200 and not ej["results"][0]["ejected"], ej
            call("/api/reset", {})
            call("/api/plan", {})
            again = wait("plan")
            assert again["new_files"] == 0 and again["already_photos"] == 5, again

            # HDR Merge: a folder is searched with its subfolders in the background, a folder on
            # a memory card is refused, and a merge of fake RAW files fails cleanly, set by set.
            make_bracket_day(os.path.join(dest, "2026", "3. March", "01Mar26"))
            assert call("/api/hdr/folder", {"path": card})[0] == 400, "a folder on a card must be refused"
            st, r = call("/api/hdr/folder", {"path": dest})
            assert st == 200, r
            st, s = call("/api/state")
            assert s["hdr_missing"] is None, s["hdr_missing"]
            assert s["hdr_folder"] == dest and s["hdr_folder_exists"], s
            call("/api/hdr/scan", {})
            scan = wait("scan", key="hdr_job")
            assert scan["sets"] == 2, scan
            st, sets = call("/api/hdr/sets")
            assert [x["folder"] for x in sets["sets"]] == [os.path.join("2026", "3. March", "01Mar26")] * 2, sets
            assert [len(x["names"]) for x in sets["sets"]] == [3, 3] and not any(x["done"] for x in sets["sets"]), sets
            st, r = call("/api/hdr/merge", {"ids": [0], "tiff": False})
            assert st == 200, r
            res = wait("merge", key="hdr_job")
            assert res["merged"] == 0 and len(res["failed"]) == 1, res
            assert not os.path.exists(os.path.join(dest, "2026", "3. March", "HDR")), "a failed merge left an HDR folder"
            assert not os.path.exists(os.path.join(dest, "2026", "3. March", "01Mar26", "HDR")), "a failed merge left an HDR folder"
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()

        # The HDR merge itself, on synthetic frames, inside this very app (bundled libraries too).
        os.remove(urlfile)
        r = subprocess.run(tool + ["--hdr-selftest"], env=env, capture_output=True, text=True, timeout=600)
        out = open(urlfile).read() if os.path.exists(urlfile) else r.stdout
        if r.returncode != 0 or out.strip() != "PASS":
            sys.exit(f"FAIL: HDR self-test: {out.strip() or r.stderr[-2000:]}")

        # On a Mac, the menu bar layer loads and draws its icons inside this app.
        if sys.platform == "darwin":
            if os.path.exists(urlfile):
                os.remove(urlfile)
            r = subprocess.run(tool + ["--menubar-check"], env=env, capture_output=True, text=True, timeout=120)
            out = open(urlfile).read() if os.path.exists(urlfile) else r.stdout
            if r.returncode != 0 or out.strip() != "PASS":
                sys.exit(f"FAIL: menu bar check: {out.strip() or r.stderr[-2000:]}")
    print("PASS")


if __name__ == "__main__":
    main()
