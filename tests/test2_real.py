#!/usr/bin/env python3
"""
TEST 2 — INSIDE THE RUNNING APP, WITH REAL DATA

Closes off "the logic is right but nothing calls it". The server is started
the way the launcher starts it, the requests go over HTTP, and the keys are
the real ones. Nothing here is mocked.

The loop is the point: Speak's own output becomes Listen's own input, so a
break on either side fails the same test.

    GEMINI_KEYS=~/.gemini_keys python3 tests/test2_real.py
"""

import json, os, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "src", "10_app.py")
PORT = os.environ.get("GTT_TEST_PORT", "7399")
BASE = "http://127.0.0.1:%s" % PORT

CHECKS = 0
fails = []


def check(name, got, want=True):
    global CHECKS
    CHECKS += 1
    if got == want:
        print("   ok   %s" % name)
    else:
        print("   FAIL %s\n        got %r, want %r" % (name, got, want))
        fails.append(name)


GUARD = {"X-Gtt-Local": "1"}


def get(path, timeout=120, headers=None):
    req = urllib.request.Request(BASE + path, headers=dict(GUARD, **(headers or {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def raw_get(path, headers=None, timeout=30):
    """No guard header, on purpose."""
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def post_json(path, obj, timeout=400):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(),
                                 headers=dict(GUARD, **{"Content-Type": "application/json"}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post_file(path, filepath, fields=None, timeout=400, field="audio"):
    boundary = "----gtt%d" % int(time.time())
    body = b""
    for k, v in (fields or {}).items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, k, v)).encode()
    body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n"
             % (boundary, field, os.path.basename(filepath))).encode()
    body += open(filepath, "rb").read() + ("\r\n--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(BASE + path, data=body,
                                 headers=dict(GUARD, **{"Content-Type":
                                              "multipart/form-data; boundary=" + boundary}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post_one(label):
    req = urllib.request.Request(BASE + "/api/key/" + urllib.parse.quote(label) + "/test",
                                 data=b"", headers=GUARD, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


print("TEST 2 — the running app, real keys, real audio")

keyfile = os.environ.get("GEMINI_KEYS", os.path.expanduser("~/.gemini_keys"))
if not os.path.exists(keyfile):
    sys.exit("   no key ring at %s, cannot run test 2" % keyfile)

env = dict(os.environ, GTTS_PORT=PORT, GEMINI_KEYS=keyfile)
proc = subprocess.Popen([sys.executable, APP], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    up = False
    for _ in range(40):
        try:
            get("/", timeout=3)
            up = True
            break
        except Exception:
            time.sleep(0.5)
    check("the server comes up on the port the launcher uses", up)
    if not up:
        raise SystemExit(1)

    code, page = get("/")
    check("the page is served", code, 200)
    check("all three tabs are in the first frame",
          all(w in page for w in (b"SPEAK", b"LISTEN", b"KEYS")))
    check("the player is drawn before there is anything to play, dimmed",
          b'<audio id="player" class="idle"' in page)
    check("the page uses the house tokens, not a set of its own",
          b"--amber:#f59e0b" in page and b"--prose:#f2ddb4" in page)
    check("each account gets a card with its own actions", b"kacts" in page)

    b = json.loads(get("/api/budget")[1].decode())
    check("the budget endpoint answers", "models" in b)
    check("it knows how long until the reset", 0 < b["reset_in"] <= 86400)
    before = sum(m["used"] for m in b["models"])

    line = "Say plainly and slowly: the fuel is still there."
    r = post_json("/api/speak", {"text": line, "voice": "Charon"})
    check("Speak returns audio", r.get("ok"), True)
    if not r.get("ok"):
        print("        %s %s" % (r.get("error"), r.get("log")))
        raise SystemExit(1)
    check("the audio has real length", r["seconds"] > 0.8)
    check("it says which key it spent", bool(r.get("key")))
    check("it says which model answered", r["model"] in
          ("gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview"))

    code, wav = get("/out/" + r["file"])
    check("the WAV is downloadable from the page", code, 200)
    check("it is a real RIFF WAVE", wav[:4] == b"RIFF" and wav[8:12] == b"WAVE")

    tmp = tempfile.mktemp(suffix=".wav")
    open(tmp, "wb").write(wav)
    t = post_file("/api/listen", tmp, {"lang": "English"})
    check("Listen returns a transcript", t.get("ok"), True)
    if t.get("ok"):
        check("the loop closes: it heard what Speak said",
              "fuel" in t["text"].lower() and "still" in t["text"].lower())
        check("it reports how much audio it heard", t["seconds"] > 0.8)
        check("Listen used an STT model, not a TTS one",
              t["model"] in ("gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.5-flash"))
    else:
        print("        %s %s" % (t.get("error"), t.get("log")))
        fails.append("listen")

    b2 = json.loads(get("/api/budget")[1].decode())
    after = sum(m["used"] for m in b2["models"])
    check("the ledger counted both calls", after >= before + 2)
    check("seconds made were written down", b2["audio_out"] > 0)
    check("seconds heard were written down", b2["audio_in"] > 0)

    h = json.loads(get("/api/health")[1].decode())
    check("health reports what is installed", h["flask"], True)
    check("health reports the ring it is using", h["keys"] > 0)
    check("health carries the version", h["version"] >= 2)

    # the picker, over HTTP, with a file shaped like nothing in particular
    # a key that has never existed and never will, different on every run so
    # the test can be run twice without the first run making the second lie
    fake = "AQ.Ab8RN6TEST" + ("%019d" % int(time.time() * 1000))
    imp = tempfile.mktemp(suffix=".md")
    open(imp, "w").write("| account | key |\n|---|---|\n| an imported one | %s |\n" % fake)
    i1 = post_file("/api/import", imp, {}, timeout=60, field="keyfile")
    check("the picker imports from a markdown table over HTTP", i1["ok"], True)
    check("it added exactly one", len(i1["added"]), 1)
    # startswith, not equals: run the gate twice and the second run's label is
    # numbered, which is the ring refusing to hold two accounts with one name
    check("it took the account name out of the table",
          i1["added"][0]["label"].startswith("an imported one"))
    check("it never returns a whole key", fake not in json.dumps(i1))
    i2 = post_file("/api/import", imp, {}, timeout=60, field="keyfile")
    check("the same file a second time adds nothing", i2["added"], [])
    check("and says it is already there", len(i2["duplicates"]), 1)
    check("the ring did not grow twice", i2["ring"], i1["ring"])
    os.remove(imp)

    # THE GUARD. A page you have open in another tab can make your browser
    # send requests here, and this app deletes keys and spends quota.
    code, _ = raw_get("/api/budget")
    check("an api call with no guard header is refused", code, 403)
    code, _ = raw_get("/", headers={})
    check("but the page itself still loads without one", code, 200)
    code, _ = raw_get("/api/budget", headers={"X-Gtt-Local": "1",
                                              "Origin": "https://somewhere.else"})
    check("a call carrying another page's Origin is refused", code, 403)
    code, _ = raw_get("/", headers={"Host": "evil.example"})
    check("a request arriving under another Host is refused", code, 403)

    ring = json.loads(get("/api/ring")[1].decode())
    check("the ring can be drawn before anything is tested", "keys" in ring)
    if ring["keys"]:
        lab = ring["keys"][0]["label"]
        one = post_one(lab)
        check("one account can be tested on its own", one.get("ok"), True)
        check("and it comes back with a verdict",
              one.get("verdict") in ("working", "busy", "no credit", "refused", "unknown"))

    rows = json.loads(get("/api/keys", timeout=180)[1].decode())
    check("every account in the ring is reported", len(rows) > 0)
    check("at least one is live", any(x["state"] == "live" for x in rows))
    check("no whole key is ever sent to the page",
          all("\u2026" in x["masked"] and len(x["masked"]) < 16 for x in rows))
    check("every row carries one of the five verdicts",
          all(x["verdict"] in ("working", "busy", "no credit", "refused", "unknown")
              for x in rows))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

print("\nTEST 2: %d checks, %d failed" % (CHECKS, len(fails)))
sys.exit(1 if fails else 0)
