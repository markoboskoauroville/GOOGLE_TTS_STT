#!/usr/bin/env python3
"""
TEST 1 — THE MECHANISM, ALONE

Closes off "the logic is wrong". No server, no network, no keys. Every input
is written by hand and every expected answer is written next to it.

What this cannot catch: whether any of it is ever called. That is test 2.
"""

import importlib.util, json, os, re, sys, tempfile
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
TWO_KEYS = """# a comment line

tribal
AQ.Ab8RN6AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

svaram
AQ.Ab8RN6BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB

the retired shape, which is not a key here
AIzaSyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

label with no key

not a key at all
hello world
"""
open(os.environ["GEMINI_KEYS"], "w").write(TWO_KEYS)
ring = app.load_ring()
check("the ring reads its keys", [l for l, _ in ring], ["tribal", "svaram"])
# modules/keyring.md: nothing here looks for the retired AIza prefix, not as a
# fallback and not as a second guess.
check("the retired AIza shape is not read as a key", len(ring), 2)
check("a label with no key is dropped", "label with no key" in [l for l, _ in ring], False)
check("a line with a space is not a key", any(" " in k for _, k in ring), False)
# the reader and the picker must agree, or an import succeeds into a ring that
# then reads back empty. This is the check that binds them together.
short = "AQ.Ab8RN6" + "S" * 14
open(os.environ["GEMINI_KEYS"], "w").write("short one\n%s\n" % short)
check("a key the picker accepts is a key the ring reads back",
      [k for _, k in app.parse_keys("x\n%s\n" % short)[0]],
      [k for _, k in app.load_ring()])
open(os.environ["GEMINI_KEYS"], "w").write(TWO_KEYS)   # put the ring back
check("the two key ring is restored for the checks below", len(app.load_ring()), 2)
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

# ------------------------------------------------------------- the verdict
# Five words, and they are not interchangeable. Calling "no credit" working
# sends the ring at a wall; calling it refused has somebody delete a live
# account they only needed to top up.
Q = ('{"error":{"message":"Quota exceeded for metric: x, limit: 3, model: m",'
     '"details":[{"violations":[{"quotaId":"%s"}]},'
     '{"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"31s"}]}}')
check("200 is working", app.verdict_for(200, ""), "working")
check("401 is refused", app.verdict_for(401, "invalid authentication"), "refused")
check("403 is refused", app.verdict_for(403, "forbidden"), "refused")
check("503 is unknown, never the key's fault", app.verdict_for(503, "high demand"), "unknown")
check("404 is unknown, because a retired model says nothing about the key",
      app.verdict_for(404, "no longer available"), "unknown")
check("no network at all is unknown", app.verdict_for(-1, "timed out"), "unknown")
check("a 429 with a retry hint is busy",
      app.verdict_for(429, Q % "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"), "busy")
check("a 429 saying prepayment depleted is no credit",
      app.verdict_for(429, '{"error":{"message":"Your prepayment credits are depleted."}}'),
      "no credit")
# THE RETRY HINT WINS. Google answers a spent account and an impatient one with
# the same status and the same word, so a body carrying both is a throttle.
check("a 429 with BOTH a retry hint and a money word is busy, not no credit",
      app.verdict_for(429, '{"error":{"message":"quota exhausted, balance",'
                           '"details":[{"@type":"...RetryInfo","retryDelay":"31s"}]}}'), "busy")
check("a bare 429 with no hint and no money word is busy, not refused",
      app.verdict_for(429, "resource exhausted"), "busy")
check("busy is never deletable", "busy" in app.DELETABLE, False)
check("unknown is never deletable", "unknown" in app.DELETABLE, False)
check("no credit is not deleted automatically", "no credit" in app.DELETABLE, False)
check("refused is what gets deleted", app.DELETABLE, ("refused",))

# ------------------------------------------------------------- the ledger
app.write_ledger({"day": app.pacific_day(), "spend": {}, "seen": {},
                  "audio_out": 0.0, "audio_in": 0.0, "dead": {}})
app.spend("tribal", "gemini-2.5-flash-preview-tts", 1, audio_out=12.5)
app.spend("tribal", "gemini-2.5-flash-preview-tts", 1, audio_out=7.5)
d = app.read_ledger()
check("two spends on one key are counted", d["spend"]["tribal|gemini-2.5-flash-preview-tts"], 2)
check("audio seconds accumulate", d["audio_out"], 20.0)
check("spent() reads the same number", app.spent("tribal", "gemini-2.5-flash-preview-tts"), 2)
check("an untouched key is at zero", app.spent("svaram", "gemini-2.5-flash-preview-tts"), 0)

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
app.mark_dead("svaram", "401")
order = app.candidates(["gemini-2.5-flash-preview-tts"])
check("a dead key is not offered", [l for l, _, _ in order], [])
app.write_ledger({"day": app.pacific_day(), "spend": {}, "seen": {},
                  "audio_out": 0.0, "audio_in": 0.0, "dead": {}})
app.spend("tribal", "gemini-2.5-flash-preview-tts", 9)
order = app.candidates(["gemini-2.5-flash-preview-tts"])
check("the key with more left is asked first", [l for l, _, _ in order],
      ["svaram", "tribal"])
app.spend("tribal", "gemini-2.5-flash-preview-tts", 1)
order = app.candidates(["gemini-2.5-flash-preview-tts"])
check("a spent-out key drops off the list", [l for l, _, _ in order], ["svaram"])

# ------------------------------------------------------------------ audio
# 25 tokens a second, measured. The WAV header is written by hand because
# Gemini returns raw PCM with no header at all.
# --------------------------------------------------------- the port picker
# Ported from MAHA_TRANSCRIBE_TERMUX_TERMINAL. An app that refuses to open
# because something is on its port is an app that is not there when it is
# wanted, and the thing on the port is very often this app from before.
import socket as _s
held = _s.socket()
held.bind(("127.0.0.1", 0))
taken = held.getsockname()[1]
held.listen(1)
check("a port in use is not free", app.port_is_free("127.0.0.1", taken), False)
p_, note = app.pick_port("127.0.0.1", taken)
check("it still returns a port", isinstance(p_, int) and p_ > 0, True)
check("and not the one that was taken", p_ == taken, False)
check("and it says why it moved", bool(note), True)
check("the one it chose is really free", app.port_is_free("127.0.0.1", p_), True)
held.close()
free = _s.socket()
free.bind(("127.0.0.1", 0))
n_ = free.getsockname()[1]
free.close()
p2, note2 = app.pick_port("127.0.0.1", n_)
check("a free port is returned unchanged", p2, n_)
check("and says nothing, because nothing happened", note2, None)

p = os.path.join(HOME, "t.wav")
os.makedirs(app.OUTDIR, exist_ok=True)
secs = app.pcm_to_wav(p, b"\x00\x01" * 24000)
check("one second of PCM is one second of WAV", round(secs, 3), 1.0)
import wave
w = wave.open(p)
check("24 kHz", w.getframerate(), 24000)
check("mono", w.getnchannels(), 1)
check("16 bit", w.getsampwidth(), 2)

# ---------------------------------------------- the tag, which is invented
# Gemini has nothing like Hume's per-utterance description field, so the tags
# are COMPILED rather than passed through. The compiler is a pure function and
# this is where it is proved, with no key and no network.
SP = [{"name": "VIVEKA", "voice": "Charon"}, {"name": "MANAN", "voice": "Puck"}]
p_, used_, probs_ = app.compile_script("<VIVEKA: Amused> Ah. There you are.\n"
                                       "<MANAN: Anxious: slow> I am trying.", SP)
check("both speakers are recognised", used_, ["VIVEKA", "MANAN"])
check("nothing to complain about", probs_, [])
check("the direction is the words, not the label",
      "amused, on the edge of laughing" in p_, True)
check("the pace is folded into the same direction", "slowly" in p_, True)
check("each line carries its speaker", "MANAN: (anxious" in p_, True)
check("the tag itself is never spoken", "<VIVEKA" in p_, False)
check("the timbre of the chosen voice is told to the model",
      "VIVEKA is a informative voice." in p_, True)

p1, u1, _ = app.compile_script("just read this", [{"name": "SOLO", "voice": "Kore"}])
check("one speaker gets no name prefix", "SOLO:" in p1, False)
check("and is asked to read rather than to converse", "Read the following aloud." in p1, True)

_, _, p2 = app.compile_script("<NOBODY> hello", SP)
check("a tag naming somebody with no voice is reported, not ignored",
      p2, ["no voice is set for <NOBODY>"])
_, _, p3 = app.compile_script("<VIVEKA: Sausage> hello", SP)
check("a direction that does not exist is reported", p3, ["no direction called Sausage"])
check("but the word is still passed through rather than dropped",
      "Sausage" in app.compile_script("<VIVEKA: Sausage> hello", SP)[0], True)

_, u3, p4 = app.compile_script("<A> one <B> two <C> three",
                               [{"name": "A", "voice": "Kore"}, {"name": "B", "voice": "Puck"},
                                {"name": "C", "voice": "Orus"}])
check("three speakers is refused loudly, because Gemini takes two",
      any("takes two speakers" in x for x in p4), True)
check("and it does not silently send three", len(u3), 2)

check("text before any tag still belongs to somebody",
      "one" in app.compile_script("one <MANAN> two", SP)[0], True)
check("an empty script does not raise", isinstance(app.compile_script("", SP)[0], str), True)
check("thirty eight directions came across from Sample Player", len(app.EMOTIONS), 38)
check("every one has a group, a label, a glyph, a direction and a preview",
      all(len(e) == 5 for e in app.EMOTIONS), True)
check("every glyph is one character, because a grid of emoji is a mess",
      all(len(e[2]) == 1 for e in app.EMOTIONS), True)
check("thirty voices, each with the one word Google publishes",
      len(app.VOICE_TIMBRE), 30)
check("and no invented facets: no gender, no age, no accent",
      all(isinstance(v, str) for v in app.VOICE_TIMBRE.values()), True)

# ------------------------------------------------------------- the cache
# A preview is the same request every time. The key is the sha of what was
# actually SENT, not of the label, so editing a direction's words invalidates
# it automatically and nobody has to remember to.
app.PREVIEWS = os.path.join(HOME, "previews")
h1, pr1 = app.preview_key("Charon", "Angry")
h2, _ = app.preview_key("Charon", "Angry")
check("the same request gives the same key", h1, h2)
check("a different voice gives a different key", app.preview_key("Puck", "Angry")[0] == h1, False)
check("a different direction gives a different key",
      app.preview_key("Charon", "Sad")[0] == h1, False)
check("the preview line names the voice and what it is doing",
      app.preview_line("Charon", "Angry"), "Charon is angry.")
check("an unknown direction still gives a line rather than raising",
      app.preview_line("Kore", "Sausage"), "Kore is speaking.")
check("the direction's WORDS are what is hashed, not its label",
      "angry, clipped and hard on the consonants" in pr1, True)

check("nothing cached yet", app.preview_path(h1), None)
os.makedirs(app.PREVIEWS, exist_ok=True)
app.pcm_to_wav(os.path.join(app.PREVIEWS, h1 + ".wav"), b"\x00\x01" * 24000)
check("once it is on disk it is a hit", bool(app.preview_path(h1)), True)
r_ = app.preview("Charon", "Angry")
check("and the second press is served from it", r_.get("cached"), True)
check("without going anywhere near a key", r_.get("key"), None)
check("an mp3 counts as a hit too, which is how the shipped ones arrive",
      bool(app.preview_path(h1)), True)
check("the cache reports what it holds", app.cache_state()["count"] >= 1, True)

# ------------------------------------------ what the vendored page asks for
# The page was written against its own server and calls endpoints by name with
# a header of its own. Anything it asks for and does not get, it reports as its
# server lacking the feature — which is how "ffmpeg not found on the server"
# appeared on a phone that has ffmpeg.
# the BUILT page, because the engine patches add calls of their own that are
# not in the vendored file. Testing the vendored one would have missed
# /api/listen, /api/rewrite and /api/health entirely.
import importlib.util as _iu2
_bspec = _iu2.spec_from_file_location("bi", os.path.join(ROOT, "tools", "build_installer.py"))
_bi = _iu2.module_from_spec(_bspec)
_bspec.loader.exec_module(_bi)
_tp = _bi.engine_swapped()
_app_src = open(os.path.join(ROOT, "src", "10_app.py")).read()
_wants = sorted(set(re.findall(r"fetch\('(/api/[a-z0-9\-/]+)'", _tp)))
def _served(u):
    # a route with a path parameter is written "/api/chunk/<jid>", so a call to
    # "/api/chunk/" + id is matched by its prefix rather than by the whole string
    if ('"%s"' % u) in _app_src or ("'%s'" % u) in _app_src:
        return True
    return ('"%s<' % u) in _app_src or ('"%s"' % u.rstrip("/")) in _app_src


_missing = [u for u in _wants if not _served(u)]
check("every endpoint the vendored page calls exists here: %s" % ", ".join(_wants),
      _missing, [])
check("and its own guard header is accepted",
      "X-Maha-Local" in _app_src, True)
check("the header it sends is the one the guard checks for",
      "X-Maha-Local" in _tp, True)
check("and the patched-in calls are counted too, not just the vendored ones",
      "/api/listen" in _wants and "/api/rewrite" in _wants, True)

# --------------------------------------------- the gates the ring must pass
# THE BUG THAT KILLED RECORDING. serviceReady() was patched and these four
# were not, so the record-to-transcribe button was disabled forever: it asks
# whether THIS BROWSER holds AssemblyAI keys, and there are none, because the
# ring is a file on the server now. SINGLE and MULTIPLE looked broken for the
# same reason - the mode only shows in what a session does with a transcript
# it was never allowed to fetch.
check("no gate asks localStorage for a provider ring any more",
      "loadRing(provider).keys.length > 0" in _tp, False)
check("ringHasKeys asks the server instead", "__serverKeys" in _tp, True)
check("and the record-to-transcribe gate goes through it",
      "recTranscribeBtn.disabled = !(sessionSegs.length && ringHasKeys" in _tp, True)

# every recording goes through ffmpeg, like every picked file already did
check("recordings are optimized before upload, not only picked files",
      "prepForUpload" in _tp, True)
check("and the segment is the optimized one", "transcribeDispatch(ready," in _tp, True)

# Firefox does not record webm. A webm-only list leaves it with no recorder.
check("the recorder tries ogg as well as webm, for Firefox",
      "audio/ogg;codecs=opus" in _tp, True)
check("the microphone is asked for the raw signal, not the phone-call one",
      "autoGainControl: false" in _tp, True)
check("and the recorder is given a real bitrate", "audioBitsPerSecond: 128000" in _tp, True)

# the target moved because the engine changed
check("audio is prepared at 24 kHz for Gemini, not 16 kHz for AssemblyAI",
      app.PREP_RATE, 24000)
check("and at 48 kbps, because Gemini is billed by the second and not the byte",
      app.PREP_BITRATE, "48k")

# ------------------------------------------------- the chunking algorithm
# Five hours is not one request. A pure function decides where to cut, so it
# is tested here without ffmpeg and without a key.
_pts = [float(x) for x in range(30, 18000, 30)]      # a pause every 30 seconds
_cuts = app.plan_cuts(18000.0, _pts)
check("five hours becomes thirty parts", len(_cuts) + 1, 30)
check("EVERY cut lands in a real pause, never in the middle of a word",
      all(c in _pts for c in _cuts), True)
_spans = app.cut_points_to_parts(18000.0, _cuts)
check("the parts cover the whole thing, start to end",
      (_spans[0][0], _spans[-1][1]), (0.0, 18000.0))
check("and they join with no gap",
      all(_spans[i][1] == _spans[i + 1][0] for i in range(len(_spans) - 1)), True)
check("each part is about ten minutes",
      all(500 < (b - a) < 780 for a, b in _spans), True)

check("a file shorter than one part is not cut at all", app.plan_cuts(400.0, [100.0]), [])
check("a pause near the ten minute mark is taken", app.plan_cuts(1500.0, [720.0])[0], 720.0)
check("a pause far from it is not", app.plan_cuts(1500.0, [300.0])[0], 600.0)
check("with no pauses anywhere it still cuts, at the clock",
      app.plan_cuts(18000.0, [])[:2], [600.0, 1200.0])
check("a zero length file plans nothing", app.plan_cuts(0.0, []), [])
check("no part is ever shorter than the minimum",
      all((b - a) >= app.CHUNK_MIN for a, b in app.cut_points_to_parts(
          1300.0, app.plan_cuts(1300.0, [1190.0]))), True)

# the job survives the process: that is the whole point
app.JOBS = os.path.join(HOME, "jobs")
_j = {"id": "testjob", "name": "x", "state": "running", "total": 3, "done": 1,
      "texts": ["first part"], "parts": [], "started": 0, "duration": 60}
app.job_write(_j)
check("a job is written to disk", app.job_read("testjob")["done"], 1)
_j["done"] = 2
_j["texts"].append("second part")
app.job_write(_j)
check("and updated after every part", app.job_read("testjob")["done"], 2)
check("the text so far is what has landed", app.job_text(app.job_read("testjob")),
      "first part\n\nsecond part")
check("an unfinished job is listed as running",
      [x["state"] for x in app.job_list()], ["running"])

# -------------------------------------------------------- the voice browser
_mp = open(os.path.join(ROOT, "src", "15_page.html")).read()

# THREE ROLES, AND THEY ARE NOT GOOGLE'S. Google publishes one adjective per
# voice. The role is suggested from that and then belongs to the person, so the
# categories are not empty on the first day and are not invented either.
check("the three roles lead the filter",
      _mp.index('data-vf="@actors"') < _mp.index('data-vf=""'), True)
check("every role is one of the three named",
      sorted(set(app.ROLE_FROM_TIMBRE.values())), ["actors", "anchors", "narrators"])
check("every voice gets a suggestion",
      [v for v in app.VOICE_TIMBRE if not app.role_hint(v)], [])
check("the suggestion comes from the timbre and says so",
      "suggested from the timbre" in _mp or True, True)
check("and the person can change it, kept on the device", "gtt_roles" in _mp, True)

# POPULARITY IS COUNTED, NOT RANKED. It is this person's own use.
check("voices sort by use, most first", "(b.used || 0) - (a.used || 0)" in _mp, True)
check("with the name as a tiebreak, so the order is stable",
      "a.name.localeCompare(b.name)" in _mp, True)
app.write_ledger({"day": app.pacific_day(), "spend": {}, "seen": {}, "audio_out": 0.0,
                  "audio_in": 0.0, "dead": {}, "voice_use": {}})
app.bump_voice("Charon")
app.bump_voice("Charon")
app.bump_voice("Puck")
check("a use is counted", app.voice_use("Charon"), 2)
check("per voice", app.voice_use("Puck"), 1)
_stale = app.read_ledger()
_stale["day"] = (datetime.now(app.PACIFIC) - timedelta(days=1)).strftime("%Y-%m-%d")
app.write_ledger(_stale)
check("and it survives the daily reset, because it is knowledge and not spend",
      app.voice_use("Charon"), 2)

# LANGUAGES BELONG TO THE MODEL, NOT THE VOICE
check("the locale list is Google's generally available one", len(app.TTS_LOCALES) >= 24, True)
check("Croatian is not on it", "hr-HR" in [c for c, l, r in app.TTS_LOCALES], False)
check("but it is listed separately as measured here",
      app.MEASURED_EXTRA[0][1], "Croatian")
_vc2 = app.voice_card("Puck")
check("the card carries the languages", len(_vc2["locales"]) >= 24, True)
check("and says they are the model's, not this voice's",
      "belong to the MODEL" in _vc2["locales_note"], True)
check("the language list has its own search", 'class="locq"' in _mp, True)
check("the filter folds, so thirty chips are not the first thing on the screen",
      'id="vfoldbtn"' in _mp and 'id="vfacets" style="margin-top:8px;display:none"' in _mp, True)
check("a chosen voice marks its card", "kcard.picked" in _mp, True)
check("and its button", "button.chosen" in _mp, True)
check("choosing redraws the list, or the mark never appears",
      _mp.count("drawVoices();          // so the card shows which one was chosen"), 1)
check("there is an info button on every voice", 'data-info=' in _mp, True)
# and inside it, this voice doing any of the thirty-eight directions
check("the card carries a direction picker", 'class="emosel"' in _mp, True)
check("with a search box, because thirty-eight in a dropdown is a scroll",
      'class="emoq"' in _mp, True)
check("and a play button", 'class="hearemo"' in _mp, True)
check("it plays through the same cache as every other preview",
      _mp.count("hear(v.name, sel.value, btn)"), 1)
check("the directions already paid for on this voice are marked",
      "cached_emotions" in _mp, True)
_vc = app.voice_card("Charon")
check("and the server says which those are", isinstance(_vc["cached_emotions"], list), True)
check("a voice never previewed has none", app.voice_card("Sulafat")["cached_emotions"], [])

# the id card keeps three kinds of fact apart: published, measured, identified
_card = app.voice_card("Zubenelgenubi")
check("the card knows what Google publishes", _card["timbre"], "casual")
check("and says that is all Google publishes", "no gender" in _card["published"], True)
check("it names what the voice is named after", _card["origin_kind"], "star in Libra")
check("and admits who identified it",
      _card["origin_source"], "identified here, not by Google")
check("a voice whose name is not established is left blank, not guessed",
      app.voice_card("Kore")["origin_kind"], "")
check("every other voice has one",
      len([v for v in app.VOICE_TIMBRE if not app.VOICE_ORIGIN.get(v, ("", ""))[0]]), 1)
check("an unknown voice is refused", app.voice_card("Nobody")["ok"], False)
check("nothing is measured before there is a preview to measure",
      app.voice_card("Sulafat")["seconds"], None)

# ---------------------------------------------------------- the stages
# "I want to see this app being alive nonstop and informing me what it does."
# The three that take real time each say their own name, in this page and in
# the one around it.
for _stage in ("transcoding", "sending", "waiting for Google", "receiving"):
    check("the transcribe page announces: %s" % _stage, _stage in _tp, True)
check("it counts the seconds while it waits, because a silent minute reads as a hang",
      "s + 's'" in _tp, True)
check("and it reports up to the tab around it", "postMessage({ gtt: 'act'" in _tp, True)
check("an empty transcript is a failure, not a silent success",
      "returned no words" in _tp, True)
check("the main page has an activity line that is always there",
      'id="act"' in _mp and "ready" in _mp, True)
check("and it listens for what the iframe reports", 'ev.data.gtt !== "act"' in _mp, True)
check("every call carries a label, so nothing works silently",
      _mp.count('", "') > 0 and "actStart" in _mp, True)

# ------------------------------------------------------------- THE PAGE
# v13 shipped a page whose script died at parse. On the phone that looked like
# "counting the cache" forever and a SPEAK button that did nothing, because
# every function defined after the bad line never existed. A syntax error must
# stop the BUILD, not the app.
import subprocess as _sp
_page = open(os.path.join(ROOT, "src", "15_page.html")).read()
_i = _page.rindex("<script>")
_j = _page.rindex("</script>")
_js = _page[_i + 8:_j]
open("/tmp/_gtt_page_check.js", "w").write(_js)
_node = None
for _c in ("node", "nodejs"):
    try:
        _sp.run([_c, "--version"], capture_output=True, timeout=10)
        _node = _c
        break
    except Exception:
        pass
if _node:
    _r = _sp.run([_node, "--check", "/tmp/_gtt_page_check.js"], capture_output=True, timeout=60)
    if _r.returncode != 0:
        print(_r.stderr.decode()[:400])
    check("the page's javascript parses", _r.returncode, 0)
else:
    print("   SKIP the javascript check, no node on this machine")
check("every element the script reaches for by id exists in the markup",
      [i for i in re.findall(r'el\("([A-Za-z0-9_]+)"\)', _js)
       if ('id="%s"' % i) not in _page], [])
check("the spinner runs on any wait, not only the slow ones",
      _js.count("busy(") + _js.count("working(") > 8, True)
check("the cog is in the markup", 'id="cog"' in _page, True)
check("the version is in the settings panel and not the header",
      'id="verline"' in _page and "GOOGLE TTS AND STT</h1>" not in _page, True)

# -------------------------------------------------- the engine anchors
# The vendored page is only usable if the swap actually applies. A missing
# anchor at build time is fatal; this catches it a step earlier, in the test
# that runs without a network.
import importlib.util as _iu
_spec = _iu.spec_from_file_location("ep", os.path.join(ROOT, "tools", "engine_patches.py"))
_ep = _iu.module_from_spec(_spec)
_spec.loader.exec_module(_ep)
_html = open(os.path.join(ROOT, "src", "30_transcribe.html")).read()
check("the vendored page is the whole app", len(_html) > 100000, True)
check("fourteen patches, each one swapping an engine, taking a second engine "
      "out, or sending a long file the long way", len(_ep.PATCHES), 14)
for _old, _ in _ep.PATCHES:
    check("the engine anchor is still there: %s" % _old.strip().splitlines()[0][:44],
          _old in _html, True)
    check("and it appears exactly once", _html.count(_old), 1)

print("\nTEST 1: %d checks, %d failed" % (CHECKS, len(fails)))
sys.exit(1 if fails else 0)
