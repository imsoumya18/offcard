#!/usr/bin/env python3
"""Updating from inside the app, on a real build: a copy that can't be verified stays as it is, and a
good download replaces the installed app and leaves it working.

Usage:  python tests/update_test.py <the release zip for this system>
"""
import hashlib, http.client, json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request, zipfile

IS_WIN, IS_MAC = os.name == "nt", sys.platform == "darwin"
PARENT = "import sys; sys.stdin.read()"     # stands in for the app: the engine leaves when this goes


def unpack(archive, into):
    if IS_MAC:
        subprocess.run(["ditto", "-x", "-k", archive, into], check=True)
        return os.path.join(into, "offcard.app")
    with zipfile.ZipFile(archive) as z:
        z.extractall(into)
    return into


def engine_of(root):
    return os.path.join(root, "engine", "OffcardEngine.exe") if IS_WIN else os.path.join(root, "Contents", "Resources", "engine", "OffcardEngine")


class Engine:
    def __init__(self, root, tmp, release, version):
        self.parent = subprocess.Popen([sys.executable, "-c", PARENT], stdin=subprocess.PIPE)
        urlfile = os.path.join(tmp, f"url-{time.time()}.json")
        env = {**os.environ, "HOME": tmp, "USERPROFILE": tmp, "OFFCARD_URL_FILE": urlfile, "OFFCARD_NO_UPDATE_CHECK": "1",
               "OFFCARD_PARENT_PID": str(self.parent.pid), "OFFCARD_RELEASES": release, "OFFCARD_NO_RELAUNCH": "1",
               "OFFCARD_TEST_UPDATE_VERSION": version}
        self.proc = subprocess.Popen([engine_of(root), "--serve", "--agent"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(900):
            if os.path.exists(urlfile) and os.path.getsize(urlfile):
                break
            if self.proc.poll() is not None:
                sys.exit(f"FAIL: the engine stopped with code {self.proc.returncode}")
            time.sleep(0.1)
        info = json.load(open(urlfile))
        self.host, self.token = urllib.parse.urlparse(info["url"]).netloc, info["token"]

    def call(self, path, body=None):
        c = http.client.HTTPConnection(self.host, timeout=60)
        c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None,
                  {"X-Token": self.token, "Host": self.host, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def wait_update(self):
        for _ in range(3600):
            j = self.call("/api/state")[1]["update_job"]
            if j and j["state"] != "running":
                return j
            time.sleep(0.1)
        sys.exit("FAIL: the update never finished")

    def leave(self):
        self.parent.kill()
        self.parent.wait()
        for _ in range(150):
            if self.proc.poll() is not None:
                return
            time.sleep(0.1)
        self.proc.kill()
        sys.exit("FAIL: the engine didn't leave with the app")


def main():
    archive = os.path.abspath(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        release = os.path.join(tmp, "release")
        os.makedirs(release)
        name = os.path.basename(archive)
        shutil.copy(archive, release)
        digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
        url = "file:" + urllib.request.pathname2url(release)
        root = unpack(archive, os.path.join(tmp, "installed"))
        version = subprocess.run([engine_of(root), "--version"], capture_output=True, text=True, timeout=120).stdout.split()[-1]
        mark = os.path.join(root, "Contents", "old-version") if IS_MAC else os.path.join(root, "old-version")
        open(mark, "w").close()

        # A download that doesn't match its checksum changes nothing, and says so.
        open(os.path.join(release, "SHA256SUMS"), "w").write(f"{'0' * 64}  {name}\n")
        e = Engine(root, tmp, url, version)
        assert e.call("/api/state")[1]["can_update"], "this build says it can't update itself"
        assert e.call("/api/update", {})[0] == 200
        j = e.wait_update()
        assert j["state"] == "error" and "checksum" in j["error"], j
        assert e.call("/api/update/apply", {})[0] == 400, "applied an update that isn't ready"
        assert os.path.exists(mark), "a bad download touched the installed app"
        stage = os.path.join(root if IS_WIN else os.path.dirname(root), ".offcard-update")
        assert not os.path.exists(stage), "a bad download left files behind"

        # A good download is checked and waits, and the app is swapped only once it quits.
        open(os.path.join(release, "SHA256SUMS"), "w").write(f"{digest}  {name}\n")
        assert e.call("/api/update", {})[0] == 200
        j = e.wait_update()
        assert j["state"] == "ready", j
        assert os.path.exists(mark), "the app was changed before it quit"
        assert e.call("/api/update/apply", {})[0] == 200
        time.sleep(1)
        assert os.path.exists(mark), "the app was changed while it was still running"
        e.leave()
        for _ in range(900):
            if not os.path.exists(mark) and not os.path.exists(stage):
                break
            time.sleep(0.1)
        else:
            sys.exit(f"FAIL: the app wasn't replaced: mark {os.path.exists(mark)}, stage {os.path.exists(stage)}")
        out = subprocess.run([engine_of(root), "--version"], capture_output=True, text=True, timeout=120).stdout
        assert version in out, out
        left = [n for n in os.listdir(root if IS_WIN else os.path.dirname(root)) if n.endswith(".old")]
        assert not left, left
        print("PASS")


if __name__ == "__main__":
    main()
