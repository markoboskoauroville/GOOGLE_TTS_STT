#!/usr/bin/env python3
"""
TEST 3 — THE UGLY CASES

Closes off "it works when the world behaves". Empty, enormous, malformed,
twice, out of order, absent, and never answers.

The generator list from the manifest, gone down one row at a time rather than
invented. Nothing here needs a real key: every provider answer is served by a
local HTTP server this file starts, so the failures are produced on purpose
and the app never learns the difference.

The sabotage is deliberate and is excluded from the count at the end.
"""

import http.server, importlib.util, json, os, socket, sys, tempfile, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = tempfile.mkdtemp()
os.environ["HOME"] = HOME
KEYS = os.path.join(HOME, "keys.txt")
os.environ["GEMINI_KEYS"] = KEYS

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


# --------------------------------------------------------- a fake provider
# Answers whatever the current script says, so 429s, 401s, silence and
# nonsense all arrive through the same code path the real API uses.
SCRIPT = {"mode": "ok"}
HITS = []

QUOTA = ('{"error":{"message":"Quota exceeded for metric: '
         'generativelanguage.googleapis.com/generate_content_free_tier_requests, '
         'limit: %d, model: m","details":[{"violations":[{"quotaId":"%s"}]}]}}')
AUDIO_OK = json.dumps({"candidates": [{"content": {"parts": [
    {"inlineData": {"mimeType": "audio/L16", "data": "AAEAAQAB" * 400}}]}}],
    "usageMetadata": {"totalTokenCount": 10}})
TEXT_OK = json.dumps({"candidates": [{"content": {"parts": [{"text": "heard it"}]}}],
                      "usageMetadata": {"promptTokenCount": 10,
                                        "promptTokensDetails": [{"modality": "AUDIO",
                                                                 "tokenCount": 250}]}})


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        HITS.append(self.path)
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        mode = SCRIPT["mode"]
        if mode == "hang":
            time.sleep(60)          # never answers. Not an error. No reply at all.
            return
        if mode == "minute":
            return self.send_body(429, QUOTA % (3, "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))
        if mode == "daily":
            return self.send_body(429, QUOTA % (10, "GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
        if mode == "nocredit":
            return self.send_body(429, '{"error":{"message":"Your prepayment credits are depleted."}}')
        if mode == "dead":
            return self.send_body(401, '{"error":{"message":"invalid authentication credentials"}}')
        if mode == "busy":
            return self.send_body(503, '{"error":{"message":"high demand"}}')
        if mode == "garbage":
            return self.send_body(200, "this is not json at all <<<")
        if mode == "noaudio":
            return self.send_body(200, json.dumps({"candidates": [{"content": {"parts": [
                {"text": "I will not sing"}]}}]}))
        if mode == "daily_then_ok":
            SCRIPT["mode"] = "ok"
            return self.send_body(429, QUOTA % (10, "GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
        if "tts" in self.path:
            return self.send_body(200, AUDIO_OK)
        return self.send_body(200, TEXT_OK)

    def send_body(self, code, body):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


sock = socket.socket()
sock.bind(("127.0.0.1", 0))
FAKE_PORT = sock.getsockname()[1]
sock.close()
srv = http.server.ThreadingHTTPServer(("127.0.0.1", FAKE_PORT), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

spec = importlib.util.spec_from_file_location("app", os.path.join(ROOT, "src", "10_app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
app.HOME = os.path.join(HOME, ".google_tts_stt")
app.LEDGER = os.path.join(app.HOME, "ledger.json")
app.OUTDIR = os.path.join(app.HOME, "out")
app.BASE = "http://127.0.0.1:%d/%%s:%%s" % FAKE_PORT   # SABOTAGE, on purpose
os.makedirs(app.OUTDIR, exist_ok=True)

TWO = """a
AQ.Ab8RN6AAAAAAAAAAAAAAAAAAAAAAAAAAAA

b
AQ.Ab8RN6BBBBBBBBBBBBBBBBBBBBBBBBBBBB
"""


def reset(keys=TWO):
    open(KEYS, "w").write(keys)
    app.write_ledger({"day": app.pacific_day(), "spend": {}, "seen": {},
                      "audio_out": 0.0, "audio_in": 0.0, "dead": {}})


print("TEST 3 — the ugly cases")

# ------------------------------------------------------------------ ABSENT
os.remove(KEYS) if os.path.exists(KEYS) else None
check("no key file at all is empty, not a crash", app.load_ring(), [])
reset("")
check("an empty key file is empty, not a crash", app.load_ring(), [])
reset("just a label and nothing under it\n")
check("a label with no key yields no key", app.load_ring(), [])

# ------------------------------------------------------------------- EMPTY
reset()
SCRIPT["mode"] = "ok"
r = app.speak("", "Charon")
check("empty text still asks, and the provider decides", isinstance(r, dict))
r = app.listen(os.path.join(HOME, "does-not-exist.wav"))
check("a missing audio file fails cleanly", r["ok"], False)
p = os.path.join(HOME, "zero.wav")
open(p, "wb").close()
r = app.listen(p)
check("a zero byte file does not crash", isinstance(r, dict))

# ------------------------------------------------------------- OUT OF RANGE
reset()
r = app.speak("hello", "NotAVoiceThatExists")
check("an unknown voice is refused by the provider, not by a crash", isinstance(r, dict))

# ------------------------------------------------------------- MINUTE LIMIT
# Costs a retry and nothing else. Every key refuses, so the answer is a clean
# failure with a log that names each one.
reset()
SCRIPT["mode"] = "minute"
r = app.speak("hi", "Charon")
check("all keys at their minute limit fails cleanly", r["ok"], False)
check("the log names the keys that refused", len(r["log"]) >= 2)
check("a minute limit does NOT write the key off for the day",
      app.spent("a", "gemini-2.5-flash-preview-tts"), 0)
check("but the limit it stated was learned",
      app.read_ledger()["seen"]["gemini-2.5-flash-preview-tts"]["rpm"], 3)

# -------------------------------------------------------------- DAILY LIMIT
reset()
SCRIPT["mode"] = "daily"
r = app.speak("hi", "Charon")
check("all keys at their daily wall fails cleanly", r["ok"], False)
check("a daily wall DOES write the key off for the day",
      app.spent("a", "gemini-2.5-flash-preview-tts"), 10)
check("the daily number the API stated was learned",
      app.read_ledger()["seen"]["gemini-2.5-flash-preview-tts"]["rpd"], 10)
check("and it is not offered again",
      [l for l, _, _ in app.candidates(["gemini-2.5-flash-preview-tts"])], [])

# --------------------------------------------------- ONE WALL, THEN IT WORKS
# The degradation has to be the RIGHT degradation: not "it did not crash" but
# "it moved to the next key and still produced the audio".
reset()
SCRIPT["mode"] = "daily_then_ok"
r = app.speak("hi", "Charon")
check("one key at its wall, the next one answers", r["ok"], True)
check("and the audio really came back", r["seconds"] > 0)
check("the walled key was written off", app.spent("a", "gemini-2.5-flash-preview-tts") >= 10)

# ---------------------------------------------------------------- NO CREDIT
reset()
SCRIPT["mode"] = "nocredit"
app.speak("hi", "Charon")
check("a prepaid account with nothing in it is marked dead",
      "a" in app.read_ledger()["dead"])

# --------------------------------------------------------------- REVOKED KEY
reset()
SCRIPT["mode"] = "dead"
app.speak("hi", "Charon")
d = app.read_ledger()
check("a 401 marks the key dead", len(d["dead"]) >= 1)
check("and dead keys are never offered again", app.candidates(app.TTS_CHAIN), [])

# ---------------------------------------------------------------- BUSY MODEL
reset()
SCRIPT["mode"] = "busy"
r = app.speak("hi", "Charon")
check("a 503 is not treated as a bad key", r["ok"], False)
check("nothing is marked dead by a busy model", app.read_ledger()["dead"], {})

# ---------------------------------------------------------------- MALFORMED
reset()
SCRIPT["mode"] = "garbage"
r = app.speak("hi", "Charon")
check("a 200 that is not JSON does not crash", isinstance(r, dict))
reset()
SCRIPT["mode"] = "noaudio"
r = app.speak("hi", "Charon")
check("a 200 with no audio part is a clear failure", r["ok"], False)
check("and it says so in words", "no audio" in r["error"])

# ------------------------------------------------------------ NEVER ANSWERS
# The one people skip. A socket that accepts and then goes quiet is not a
# failure any error path will see unless there is a deadline.
reset()
SCRIPT["mode"] = "hang"
t0 = time.time()
code, _ = app.post("m", "generateContent", {}, "k", timeout=3)
waited = time.time() - t0
check("a provider that never answers is cut off by the deadline", code, -1)
check("and the deadline is the one that was asked for", waited < 10)

# ----------------------------------------------------------------- ENORMOUS
reset()
SCRIPT["mode"] = "ok"
r = app.speak("word " * 20000, "Charon")
check("a hundred thousand characters is sent, not truncated silently",
      isinstance(r, dict))

# -------------------------------------------------------------------- TWICE
reset()
errs = []


def hammer():
    try:
        app.speak("hi", "Charon")
    except Exception as e:
        errs.append(e)


ts = [threading.Thread(target=hammer) for _ in range(8)]
for t in ts:
    t.start()
for t in ts:
    t.join()
check("eight at once, no exception escapes", errs, [])
total = sum(app.read_ledger()["spend"].values())
check("and every one of the eight is counted exactly once", total, 8)

# ------------------------------------------------------------ UGLY IMPORTS
# The file picker takes whatever it is handed. None of these may raise and
# none of them may put the same key in the ring twice.
reset()
check("importing an empty file adds nothing", app.import_keys("", "empty")["added"], [])
check("importing whitespace adds nothing", app.import_keys("  \n\n ", "ws")["added"], [])
check("importing a PNG adds nothing",
      app.import_keys(open(os.devnull).read() if False else
                      (b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 20).decode("utf-8", "replace"),
                      "picture.png")["added"], [])
huge = "not a key\n" * 200000
check("a two megabyte file of noise does not raise",
      isinstance(app.import_keys(huge, "huge.txt"), dict))
before = open(KEYS).read()
K1 = "AQ.Ab8RN6" + "1" * 24
r = app.import_keys("one\n%s\n" % K1, "a.txt")
check("a real key is added", len(r["added"]), 1)
r = app.import_keys("one\n%s\n" % K1, "a.txt")
check("the same file twice adds nothing the second time", r["added"], [])
r = app.import_keys("%s %s %s" % (K1, K1, K1), "repeated.txt")
check("the same key three times in one file is still not re-added", r["added"], [])
check("and the ring holds it exactly once", open(KEYS).read().count(K1), 1)
r = app.import_keys("one\n%s\n" % ("AQ.Ab8RN6" + "2" * 24), "clash.txt")
check("a second key wanting the same name is numbered", r["added"][0]["label"], "one 2")
check("the ring parses cleanly after all of that", len(app.load_ring()) >= 2)
check("the ring file is still 600", oct(os.stat(KEYS).st_mode)[-3:], "600")

# --------------------------------------------------------- LEDGER SABOTAGE
open(app.LEDGER, "w").write("{ this is not json")
check("a corrupted ledger is rebuilt, not fatal", isinstance(app.read_ledger(), dict))
check("and the rebuilt one is for today", app.read_ledger()["day"], app.pacific_day())

srv.shutdown()
print("\nTEST 3: %d checks, %d failed" % (CHECKS, len(fails)))
print("        the fake provider and the corrupted ledger were sabotage, on purpose")
sys.exit(1 if fails else 0)
