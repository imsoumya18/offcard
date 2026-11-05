#!/usr/bin/env python3
"""The engine started with --agent exits when the app that started it goes, on every system.

Usage:  python tests/agent_test.py <command to run the engine...>
  e.g.  python tests/agent_test.py python offcard.py
"""
import json, os, subprocess, sys, tempfile, time

APP = """
import json, os, subprocess, sys
tool, urlfile = json.loads(sys.argv[1]), sys.argv[2]
env = {**os.environ, "OFFCARD_URL_FILE": urlfile, "OFFCARD_NO_UPDATE_CHECK": "1", "OFFCARD_PARENT_PID": str(os.getpid())}
child = subprocess.Popen(tool + ["--serve", "--agent"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(child.pid, flush=True)
sys.stdin.read()    # lives until the test closes this
"""


def alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    tool = sys.argv[1:]
    if not tool:
        sys.exit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        urlfile = os.path.join(tmp, "url.json")
        app = subprocess.Popen([sys.executable, "-c", APP, json.dumps(tool), urlfile], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, text=True, env={**os.environ, "HOME": tmp, "USERPROFILE": tmp})
        pid = int(app.stdout.readline())
        for _ in range(600):
            if os.path.exists(urlfile) and os.path.getsize(urlfile):
                break
            time.sleep(0.1)
        else:
            sys.exit("FAIL: the engine never started")
        if not alive(pid):
            sys.exit("FAIL: the engine stopped while the app was running")
        json.load(open(urlfile))
        app.kill()
        app.wait()
        for _ in range(100):
            if not alive(pid):
                print("PASS: the engine left with the app")
                return
            time.sleep(0.1)
        subprocess.run(["taskkill", "/F", "/PID", str(pid)] if os.name == "nt" else ["kill", "-9", str(pid)])
        sys.exit("FAIL: the engine kept running after the app went")


if __name__ == "__main__":
    main()
