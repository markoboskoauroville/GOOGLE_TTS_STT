#!/usr/bin/env python3
"""
TEST 1 — THE MECHANISM, ALONE

Closes off "the logic is wrong". No server, no network, no keys. Every input
is written by hand and every expected answer is written next to it.

What this cannot catch: whether any of it is ever called. That is test 2.
"""

import importlib.util, json, os, sys, tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = tempfile.mkdtemp()
os.environ["HOME"] = HOME
os.environ["GEMINI_KEYS"] = os.path.join(HOME, "keys.txt")

spec = importlib.util.spec_from_file_location("app", os.path.join(ROOT, "src", "10_app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
app.HOME = os.path.join(HOME, ".google_tts_stt")
app.LEDGER = os.path.join(app.HOME, "ledger.json")
app.OUTDIR = os.path.join(app.HOME, "out")

fails = []


CHECKS = 0


def check(name, got, want):
    global CHECKS
    CHECKS += 1
    if got == want:
        print("   ok   %s" % name)
    else:
        print("   FAIL %s\n        got  %r\n        want %r" % (name, got, want))
        fails.append(name)


print("TEST 1 — the mechanism, alone")

# ---------------------------------------------------------------- key ring
# Both Gemini key formats, plus the things that are not keys. A filter written
# for AIza alone finds nothing in a file full of AQ. keys, and that exact
# mistake is what leaked a key once. So both, and nothing else.
open(os.environ["GEMINI_KEYS"], "w").write("""# a comment line

tribal
AQ.Ab8RN6AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

old format
AIzaSyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

label with no key

not a key at all
hello world
""")
ring = app.load_ring()
check("ring finds both key formats", [l for l, _ in ring], ["tribal", "old format"])
check("a label with no key is dropped", len(ring), 2)
check("a line with a space is not a key", any(" " in k for _, k in ring), False)
masked = app.mask("AQ.Ab8RN6QWERTYUIOPASDFGH")
check("masking keeps six at the front and four at the back", masked, "AQ.Ab8\u2026DFGH")
check("masking drops the middle", "RN6QWERTYUIOPAS" in masked, False)

# ----------------------------------------------------------- quota parsing
# A 429 states the number it just refused you. Reading it wrong in either
# direction is expensive: mistake a minute limit for a daily one and the key
# is written off for the whole day.
minute = json.dumps({"error": {"message":
    "Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 5, model: gemini-3.6-flash",
    "details": [{"violations": [{"quotaId":
        "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}})
daily = minute.replace("PerMinutePerProjectPerModel", "PerDayPerProjectPerModel") \
              .replace("limit: 5", "limit: 10")
check("minute limit is read as a minute limit", app.read_quota(minute), {"rpm": 5})
check("daily limit is read as a daily limit", app.read_quota(daily), {"rpd": 10})
check("a 401 body yields nothing", app.read_quota("not json at all"), {})
check("an empty body yields nothing", app.read_quota(""), {})
check("PerDay is daily", app.is_daily("GenerateRequestsPerDayPerProjectPerModel-FreeTier"), True)
check("PerMinute is not daily", app.is_daily("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"), False)
check("an empty quota id is not daily", app.is_daily(""), False)

# ------------------------------------------------------------- the ledger
app.write_ledger({"day": app.pacific_day(), "spend": {}, "seen": {},
                  "audio_out": 0.0, "audio_in": 0.0, "dead": {}})
app.spend("tribal", "gemini-2.5-flash-preview-tts", 1, audio_out=12.5)
app.spend("tribal", "gemini-2.5-flash-preview-tts", 1, audio_out=7.5)
d = app.read_ledger()
check("two spends on one key are counted", d["spend"]["tribal|gemini-2.5-flash-preview-tts"], 2)
check("audio seconds accumulate", d["audio_out"], 20.0)
check("spent() reads the same number", app.spent("tribal", "gemini-2.5-flash-preview-tts"), 2)
check("an untouched key is at zero", app.spent("old format", "gemini-2.5-flash-preview-tts"), 0)

# ------------------------------------------------- the boundary at midnight
# The whole point of the ledger is that it is wiped the first time it is read
# on a new Pacific day. If this is wrong the app either refuses to work after
# a reset that already happened, or keeps spending against a budget it has
# already used.
stale = app.read_ledger()
stale["day"] = (datetime.now(app.PACIFIC) - timedelta(days=1)).strftime("%Y-%m-%d")
stale["spend"]["tribal|gemini-2.5-flash-preview-tts"] = 10
stale["seen"]["gemini-2.5-flash-preview-tts"] = {"rpd": 10}
app.write_ledger(stale)
fresh = app.read_ledger()
check("yesterday's spend is cleared", fresh["spend"], {})
check("today's date is written in", fresh["day"], app.pacific_day())
check("what was LEARNED about limits survives the reset",
      fresh["seen"]["gemini-2.5-flash-preview-tts"]["rpd"], 10)
check("the countdown to reset is inside one day", 0 < app.seconds_to_reset() <= 86400, True)

# -------------------------------------------------------------- budgeting
app.write_ledger({"day": app.pacific_day(), "spend": {}, "seen": {},
                  "audio_out": 0.0, "audio_in": 0.0, "dead": {}})
b = app.budget()
tts = [m for m in b["models"] if m["model"] == "gemini-2.5-flash-preview-tts"][0]
check("two live keys times ten a day is twenty", tts["total"], 20)
check("nothing spent yet", tts["used"], 0)
check("the measured daily limit is marked measured", tts["measured"], True)
lite = [m for m in b["models"] if m["model"] == "gemini-3.1-flash-lite"][0]
check("an unmeasured daily limit is marked as a guess", lite["measured"], False)

app.spend("tribal", "gemini-2.5-flash-preview-tts", 10)
b = app.budget()
tts = [m for m in b["models"] if m["model"] == "gemini-2.5-flash-preview-tts"][0]
check("a key at its wall removes exactly its own share", tts["left"], 10)

# ------------------------------------------------------ fallback ordering
# candidates() decides who is asked next. The most budget first, dead keys
# never, and a key with nothing left never appears at all.
app.mark_dead("old format", "401")
order = app.candidates(["gemini-2.5-flash-preview-tts"])
check("a dead key is not offered", [l for l, _, _ in order], [])
app.write_ledger({"day": app.pacific_day(), "spend": {}, "seen": {},
                  "audio_out": 0.0, "audio_in": 0.0, "dead": {}})
app.spend("tribal", "gemini-2.5-flash-preview-tts", 9)
order = app.candidates(["gemini-2.5-flash-preview-tts"])
check("the key with more left is asked first", [l for l, _, _ in order],
      ["old format", "tribal"])
app.spend("tribal", "gemini-2.5-flash-preview-tts", 1)
order = app.candidates(["gemini-2.5-flash-preview-tts"])
check("a spent-out key drops off the list", [l for l, _, _ in order], ["old format"])

# ------------------------------------------------------------------ audio
# 25 tokens a second, measured. The WAV header is written by hand because
# Gemini returns raw PCM with no header at all.
p = os.path.join(HOME, "t.wav")
os.makedirs(app.OUTDIR, exist_ok=True)
secs = app.pcm_to_wav(p, b"\x00\x01" * 24000)
check("one second of PCM is one second of WAV", round(secs, 3), 1.0)
import wave
w = wave.open(p)
check("24 kHz", w.getframerate(), 24000)
check("mono", w.getnchannels(), 1)
check("16 bit", w.getsampwidth(), 2)

print("\nTEST 1: %d checks, %d failed" % (CHECKS, len(fails)))
sys.exit(1 if fails else 0)
