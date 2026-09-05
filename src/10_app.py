#!/usr/bin/env python3
"""
GOOGLE TTS AND STT  v1
One app, two faces. Speak turns text into audio. Listen turns audio into text.
Both run on the same Gemini free-tier key ring, and neither can spend the
other's daily budget without the Keys tab knowing about it.

    Speak    the MA Reader side. Text in, WAV out, thirty voices, style
             direction in plain English, two speakers in one pass.
    Listen   the Maha Transcribe side. Audio in, transcript out.
    Keys     every key tested, every limit measured, budget left today.

RUN
    pip install flask --break-system-packages     (Termux: pip install flask)
    python3 app.py                                then open localhost:7311
    python3 app.py test                           four tests, real keys

KEY RING
    ~/.gemini_keys, label line, key line, blank line. Same file gemini_vo.py
    and gemini_quota.py use. Override with GEMINI_KEYS=/path.

THE THING THAT MATTERS
    Google's free daily limits are small and they are per model per project:
    ten TTS requests a day, twenty on gemini-3.6-flash. Eighteen keys is
    eighteen separate projects, so eighteen separate daily budgets, and the
    only way to use them is to rotate. This app rotates on every request and
    writes down what it spent. Nothing else here is complicated.

    RPD resets at midnight Pacific. That is 09:00 Zagreb in winter and 09:00
    in summer too, because both shift together. The clock in the Keys tab
    counts down to it.
"""

import base64, hashlib, json, os, re, select, socket, subprocess, sys, tempfile, threading, time
import urllib.error, urllib.request, wave
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:
    PACIFIC = timezone(timedelta(hours=-8))

VERSION = 15
PORT = int(os.environ.get("GTTS_PORT", "7311"))
KEYFILE = os.environ.get("GEMINI_KEYS", os.path.expanduser("~/.gemini_keys"))
HOME = os.path.expanduser("~/.google_tts_stt")
LEDGER = os.path.join(HOME, "ledger.json")
GRAVEYARD = os.path.join(HOME, "removed_keys")
PREVIEWS = os.path.join(HOME, "previews")
OUTDIR = os.path.join(HOME, "out")
BASE = "https://generativelanguage.googleapis.com/v1beta/models/%s:%s"

# Measured on 5.9.2026 by tripping each quota and reading the number out of the
# 429. RPD None means it was never reached, so it is higher than the note says.
LIMITS = {
    "gemini-2.5-flash-preview-tts": {"rpm": 3, "rpd": 10, "use": "tts"},
    "gemini-3.1-flash-tts-preview": {"rpm": 3, "rpd": 10, "use": "tts"},
    "gemini-3.1-flash-lite":        {"rpm": 15, "rpd": None, "use": "stt"},
    "gemini-3.6-flash":             {"rpm": 5, "rpd": 20, "use": "stt"},
    "gemini-3.5-flash":             {"rpm": 5, "rpd": 20, "use": "stt"},
}
TTS_CHAIN = ["gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview"]
STT_CHAIN = ["gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.5-flash"]
RPD_UNKNOWN_ASSUMED = 50   # what we assume for budget maths when rpd is None

VOICES = ["Charon", "Puck", "Orus", "Gacrux", "Iapetus", "Fenrir", "Achird",
          "Zephyr", "Kore", "Leda", "Aoede", "Rasalgethi", "Algieba", "Sulafat",
          "Enceladus", "Achernar", "Alnilam", "Schedar", "Umbriel", "Despina",
          "Erinome", "Algenib", "Laomedeia", "Autonoe", "Callirrhoe",
          "Pulcherrima", "Zubenelgenubi", "Vindemiatrix", "Sadachbia",
          "Sadaltager"]

_lock = threading.Lock()


# ----------------------------------------------------------------- key ring

# ONE definition of what a key looks like, used by the ring reader and by the
# file picker. v2 had two, twenty characters apart, and a key that fell between
# them imported successfully into a ring that then read back empty.
#
# `AQ.` AND NOTHING ELSE. modules/keyring.md, "GEMINI KEYS START WITH AQ.":
# no tool, script or detector in this project looks for the old `AIza` prefix,
# not as a fallback, not as a second guess, not in a comment as an example,
# because a detector that knows both keeps the dead form alive in everybody's
# memory. v3 to v5 of this app kept reading AIza and were wrong to.
#
# This does not break the other rule, NEVER DROP A KEY FOR ITS SHAPE. Shape
# only decides what is IMPORTED. Anything else long and opaque is reported as
# a maybe rather than swallowed, so nothing is ever lost in silence — including
# an old AIza key, which is now shown as an unknown shape and left to you.
KEY_RE = re.compile(r"(AQ\.[A-Za-z0-9_\-]{20,})")


def load_ring():
    if not os.path.exists(KEYFILE):
        return []
    lines = [l.strip() for l in open(KEYFILE).read().splitlines()]
    out, i = [], 0
    while i < len(lines) - 1:
        if lines[i] and KEY_RE.fullmatch(lines[i + 1]):
            out.append((lines[i], lines[i + 1]))
            i += 2
        else:
            i += 1
    return out


def mask(key):
    return key[:6] + "…" + key[-4:]


# ------------------------------------------------------- the file picker
#
# Keys arrive in whatever shape they were saved in: a note with the account
# name above each key, a .env, a JSON export, a CSV, a markdown table, a
# screenshot's OCR, a WhatsApp message pasted into a text file. The parser's
# job is to find the keys in any of those without being told which it is, take
# the account names where they exist, invent them where they do not, and never
# fall over on a file that turns out to be a PDF.
#
# It is deliberately in two halves. FINDING keys is a regex over the raw text
# and is never wrong about what a key looks like. NAMING them is guesswork, and
# guesswork is allowed to be wrong because a wrong label costs nothing — the
# key still works and the label can be edited. Keeping the two apart means a
# clever labelling idea can never lose a key.

# KEY_RE is defined once, above load_ring, and both halves of this file use
# that one. Getting the prefix wrong is not a small mistake: a redaction filter
# that does not match the key it is redacting prints the key, which is how one
# ended up in a chat transcript on the first command of the session that built
# this app.

# Google has changed the format once and will change it again. This catches a
# line that is nothing but one long opaque token, so a third format is
# REPORTED rather than silently dropped. It is never imported on its own.
MAYBE_RE = re.compile(r"^[A-Za-z0-9_\-\.]{32,}$")
NOT_A_KEY = re.compile(r"^(?:[0-9a-f]{32,}|[A-Za-z0-9+/]+={1,2}|https?[:/].*)$", re.I)
# An old-format key is now an unknown shape like any other: reported, never
# imported, never silently dropped.

LABEL_SEP = re.compile(r"^\s*[\"'\[\|\-\*\d\.\)]*\s*(.{1,60}?)\s*[\"']?\s*[:=,\|]\s*[\"']?$")
MAX_IMPORT_BYTES = 8 * 1024 * 1024


def clean_label(raw):
    """Whatever surrounded the name in the original file, take it off."""
    if not raw:
        return ""
    s = raw.strip()
    s = re.sub(r"^[\s>#\-\*\u2022\|,;:=]+", "", s)       # markdown, bullets, pipes, stray commas
    s = re.sub(r"[\s\|,:=;]+$", "", s)
    s = s.strip().strip("\"'`").strip()
    # GEMINI_API_KEY_TRIBAL is called tribal. Strip the noise words one at a
    # time, because they come stacked and one pass leaves half of them behind.
    for _ in range(4):
        s2 = re.sub(r"^(api|key|token|secret|gemini|google|account|name)[\s_\-:=]*", "",
                    s, flags=re.I)
        if s2 == s:
            break
        s = s2
    s = s.strip(" _-:=").strip()
    s = re.sub(r"\s+", " ", s)
    if KEY_RE.search(s) or len(s) > 40:
        return ""
    if not re.search(r"[A-Za-z0-9]", s):
        return ""
    return s


def label_before(text, start, lines, line_no):
    """Three places a name hides, in the order they are trustworthy."""
    line = lines[line_no]
    col = start - sum(len(l) + 1 for l in lines[:line_no])

    # 1. on the same line, in front of the key:  tribal: AQ...   "tribal","AQ..."
    head = line[:col]
    if head.strip():
        m = LABEL_SEP.match(head)
        cand = clean_label(m.group(1) if m else head)
        if cand:
            return cand

    # 2. on the same line, after the key:  AQ...,tribal   | AQ... | tribal |
    tail = line[col:]
    tail = KEY_RE.sub("", tail, count=1)
    cand = clean_label(tail)
    if cand:
        return cand

    # 3. the nearest line above that is not blank and holds no key of its own
    for j in range(line_no - 1, max(line_no - 4, -1), -1):
        prev = lines[j]
        if not prev.strip() or KEY_RE.search(prev):
            continue
        if re.match(r"^\s*(#|//|;)", prev):      # a comment is not an account name
            break
        cand = clean_label(prev)
        if cand:
            return cand
        break
    return ""


def parse_keys(text):
    """Find every key in any text. Returns (pairs, maybes).

    pairs is [(label, key)] in the order they appear, one entry per DISTINCT
    key — a key written twice in one file is one key. maybes is a list of
    long opaque tokens that look like they could be a format we do not know.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    lines = text.splitlines()
    starts, pos = [], 0
    for l in lines:
        starts.append(pos)
        pos += len(l) + 1

    pairs, seen = [], set()
    for m in KEY_RE.finditer(text):
        key = m.group(1)
        if key in seen:
            continue
        seen.add(key)
        line_no = 0
        for i, s in enumerate(starts):
            if s <= m.start():
                line_no = i
            else:
                break
        pairs.append((label_before(text, m.start(), lines, line_no), key))

    maybes = []
    for l in lines:
        s = l.strip().strip("\"',")
        if (MAYBE_RE.match(s) and not KEY_RE.search(s)
                and not NOT_A_KEY.match(s) and s not in maybes):
            maybes.append(s)

    # A JSON export names its keys better than the line above ever could, and
    # the line above a key inside JSON is a fragment of JSON. So when the whole
    # file parses, the JSON names REPLACE the line-based guesses rather than
    # filling in beside them.
    #
    # Two shapes, both common:
    #     {"tribal": "AQ..."}                     the dict key is the name
    #     {"name": "tribal", "key": "AQ..."}      a sibling field is the name
    # The second one is why a plain dict-key lookup is not enough: the key
    # holding the key is called "key", which strips to nothing.
    NAME_FIELDS = ("name", "label", "account", "title", "id", "alias")
    try:
        obj = json.loads(text)
        named = {}

        def walk(node, name="", sibling=""):
            if isinstance(node, dict):
                sib = ""
                for f in NAME_FIELDS:
                    for k, v in node.items():
                        if k.lower() == f and isinstance(v, str) and not KEY_RE.search(v):
                            sib = v
                            break
                    if sib:
                        break
                for k, v in node.items():
                    walk(v, str(k), sib)
            elif isinstance(node, list):
                for v in node:
                    walk(v, name, sibling)
            elif isinstance(node, str):
                for mm in KEY_RE.finditer(node):
                    named[mm.group(1)] = clean_label(name) or clean_label(sibling)

        walk(obj)
        if named:
            pairs = [(named.get(k, ""), k) for _, k in pairs]
    except Exception:
        pass

    return pairs, maybes


def unique_label(label, taken, n):
    """A name already in use gets a number, so two accounts never share one."""
    base = label or ("account %d" % n)
    if base not in taken:
        return base
    i = 2
    while "%s %d" % (base, i) in taken:
        i += 1
    return "%s %d" % (base, i)


def import_keys(text, source_name=""):
    """Merge new keys into the ring. Existing keys are never touched, never
    rewritten, and never duplicated. The file is appended to, so comments and
    the order already in it survive."""
    pairs, maybes = parse_keys(text)
    existing = load_ring()
    have = {k for _, k in existing}
    taken = {l for l, _ in existing}

    added, dupes = [], []
    n = len(existing)
    for label, key in pairs:
        if key in have:
            dupes.append({"label": next((l for l, k in existing if k == key), ""),
                          "masked": mask(key)})
            continue
        n += 1
        lab = unique_label(label, taken, n)
        taken.add(lab)
        have.add(key)
        added.append((lab, key))

    if added:
        os.makedirs(os.path.dirname(KEYFILE) or ".", exist_ok=True)
        old = open(KEYFILE).read() if os.path.exists(KEYFILE) else ""
        if old and not old.endswith("\n"):
            old += "\n"
        if old and not old.endswith("\n\n"):
            old += "\n"
        block = "".join("%s\n%s\n\n" % (l, k) for l, k in added)
        tmp = KEYFILE + ".new"
        with open(tmp, "w") as f:
            f.write(old + block)
        os.chmod(tmp, 0o600)
        os.replace(tmp, KEYFILE)          # rename, never truncate
        os.chmod(KEYFILE, 0o600)
        receipt(source_name, added, dupes, maybes)

    return {"ok": True,
            "found": len(pairs),
            "added": [{"label": l, "masked": mask(k),
                       } for l, k in added],
            "duplicates": dupes,
            "maybes": [m[:6] + "\u2026" for m in maybes],
            "ring": len(load_ring()),
            "source": source_name}


def receipt(source_name, added, dupes, maybes):
    """A record of what was imported, with no key in it. The keys themselves
    live in exactly one place and this is not that place."""
    d = os.path.join(HOME, "imports")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, time.strftime("%Y%m%d_%H%M%S") + ".txt")
    with open(p, "w") as f:
        f.write("imported %s\nfrom %s\n\n" % (time.strftime("%d.%m.%Y %H:%M"), source_name or "?"))
        for l, k in added:
            f.write("  added    %-24s %s\n" % (l, mask(k)))
        for x in dupes:
            f.write("  already  %-24s %s\n" % (x["label"], x["masked"]))
        for m in maybes:
            f.write("  unknown format, not imported: %s\u2026\n" % m[:6])
    os.chmod(p, 0o600)


# ------------------------------------------------------------------ ledger

def pacific_day():
    return datetime.now(PACIFIC).strftime("%Y-%m-%d")


def seconds_to_reset():
    now = datetime.now(PACIFIC)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((nxt - now).total_seconds())


def read_ledger():
    if not os.path.exists(LEDGER):
        return {"day": pacific_day(), "spend": {}, "seen": {}, "audio_out": 0.0,
                "audio_in": 0.0, "dead": {}}
    try:
        d = json.load(open(LEDGER))
    except Exception:
        d = {}
    if d.get("day") != pacific_day():
        # midnight Pacific happened. Everything Google counts is back to zero.
        d = {"day": pacific_day(), "spend": {}, "seen": d.get("seen", {}),
             "audio_out": 0.0, "audio_in": 0.0, "dead": d.get("dead", {})}
        write_ledger(d)
    d.setdefault("spend", {})
    d.setdefault("seen", {})
    d.setdefault("dead", {})
    d.setdefault("audio_out", 0.0)
    d.setdefault("audio_in", 0.0)
    return d


def write_ledger(d):
    os.makedirs(HOME, exist_ok=True)
    tmp = LEDGER + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1)
    os.replace(tmp, LEDGER)


def spend(label, model, n=1, audio_out=0.0, audio_in=0.0):
    with _lock:
        d = read_ledger()
        k = "%s|%s" % (label, model)
        d["spend"][k] = d["spend"].get(k, 0) + n
        d["audio_out"] += audio_out
        d["audio_in"] += audio_in
        write_ledger(d)


def note_limit(model, rpd=None, rpm=None):
    with _lock:
        d = read_ledger()
        s = d["seen"].setdefault(model, {})
        if rpd:
            s["rpd"] = rpd
        if rpm:
            s["rpm"] = rpm
        write_ledger(d)


def limit_for(model, which):
    d = read_ledger()
    seen = d["seen"].get(model, {})
    if seen.get(which):
        return seen[which]
    v = LIMITS.get(model, {}).get(which)
    if which == "rpd" and v is None:
        return RPD_UNKNOWN_ASSUMED
    return v or 0


def spent(label, model):
    return read_ledger()["spend"].get("%s|%s" % (label, model), 0)


def mark_dead(label, why):
    with _lock:
        d = read_ledger()
        d["dead"][label] = why
        write_ledger(d)


# --------------------------------------------------------------- API calls

def post(model, verb, payload, key, timeout=300):
    req = urllib.request.Request(
        BASE % (model, verb), data=json.dumps(payload).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode()
        except Exception:
            return e.code, ""
    except Exception as ex:
        return -1, str(ex)[:200]


def is_daily(quota_id):
    """PerDay writes a key off until midnight Pacific. PerMinute costs a retry.
    Kept as its own function so it can be tested without a server."""
    return "PerDay" in (quota_id or "")


def read_quota(body):
    """A 429 tells you the number it refused you. Take it.

    Parse the JSON first. An earlier version read the quotaId with a regex that
    expected a space after the colon, which is how Google pretty-prints it, and
    so it worked against the real API and quietly read every daily wall as a
    minute limit anywhere the JSON was compact. Test 3 found that. The regex is
    still here, but only for a body that will not parse at all."""
    out = {}
    try:
        err = json.loads(body or "")["error"]
        for det in err.get("details", []):
            for v in det.get("violations", []):
                qid = v.get("quotaId", "")
                m = re.search(r"limit: (\d+)", err.get("message", ""))
                n = int(v["quotaValue"]) if v.get("quotaValue") else (int(m.group(1)) if m else 0)
                if n:
                    out["rpd" if is_daily(qid) else "rpm"] = n
        if out:
            return out
        m = re.search(r"limit: (\d+)", err.get("message", ""))
        if m:
            out["rpm"] = int(m.group(1))
        return out
    except Exception:
        pass
    nums = re.findall(r"metric: \S+, limit: (\d+)", body or "")
    ids = re.findall(r'"quotaId":\s*"([^"]+)"', body or "")
    for qid, n in zip(ids, nums):
        out["rpd" if is_daily(qid) else "rpm"] = int(n)
    if nums and not ids:
        out["rpm"] = int(nums[0])
    return out


def candidates(chain):
    """(label, key, model) ordered by budget left, most first. Skips anything
    the ledger already knows is dead or spent out."""
    d = read_ledger()
    ring = [(l, k) for l, k in load_ring() if l not in d["dead"]]
    out = []
    for model in chain:
        cap = limit_for(model, "rpd")
        for label, key in ring:
            left = cap - d["spend"].get("%s|%s" % (label, model), 0)
            if left > 0:
                out.append((left, label, key, model))
    out.sort(key=lambda x: -x[0])
    return [(l, k, m) for _, l, k, m in out]


def with_fallback(chain, build_payload, verb="generateContent", tries=40):
    """Walks the ring. A 429 costs nothing but a retry, and teaches the ledger."""
    log = []
    for label, key, model in candidates(chain)[:tries]:
        code, body = post(model, verb, build_payload(model), key)
        if code == 200:
            spend(label, model)
            return {"ok": True, "data": body, "label": label, "model": model, "log": log}
        if code == 429 and isinstance(body, str) and "prepayment" in body:
            # A prepaid account with an empty balance answers 429 like a rate
            # limit does. It is not one: waiting will never help. Test 3 caught
            # this being retried forever because the rate-limit branch ran first.
            mark_dead(label, "no credit")
            log.append("%s has no credit" % label)
            continue
        if code == 429:
            q = read_quota(body if isinstance(body, str) else "")
            if q.get("rpd"):
                note_limit(model, rpd=q["rpd"])
                # this key is finished for today on this model
                with _lock:
                    d = read_ledger()
                    d["spend"]["%s|%s" % (label, model)] = q["rpd"]
                    write_ledger(d)
                log.append("%s/%s at daily wall (%d)" % (label, model, q["rpd"]))
            else:
                if q.get("rpm"):
                    note_limit(model, rpm=q["rpm"])
                log.append("%s/%s minute limit, moving on" % (label, model))
            continue
        if code == 401:
            mark_dead(label, "401 invalid key")
            log.append("%s is dead" % label)
            continue
        if code == 503:
            log.append("%s/%s busy" % (label, model))
            continue
        log.append("%s/%s HTTP %s" % (label, model, code))
    return {"ok": False, "error": "every key and model refused", "log": log}


# ------------------------------------------------------------------- SPEAK

def pcm_to_wav(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return len(pcm) / 2 / 24000


# The thirty prebuilt Gemini voices and the one word Google publishes for each.
#
# Roles.kt's lesson, kept: A BLANK IS A FACT, A GUESS IS NOT. Hume publishes four
# tags per voice and Sample Player still had to read the NAMES to find the role,
# because the tags did not carry it. Google publishes one adjective and nothing
# else - no gender, no age, no accent - so those facets do not exist here rather
# than being invented from the sound of a name. The filter is the search box,
# the timbre, and what you have starred.
VOICE_TIMBRE = {
    "Zephyr": "bright", "Puck": "upbeat", "Charon": "informative", "Kore": "firm",
    "Fenrir": "excitable", "Leda": "youthful", "Orus": "firm", "Aoede": "breezy",
    "Callirrhoe": "easy going", "Autonoe": "bright", "Enceladus": "breathy",
    "Iapetus": "clear", "Umbriel": "easy going", "Algieba": "smooth",
    "Despina": "smooth", "Erinome": "clear", "Algenib": "gravelly",
    "Rasalgethi": "informative", "Laomedeia": "upbeat", "Achernar": "soft",
    "Alnilam": "firm", "Schedar": "even", "Gacrux": "mature",
    "Pulcherrima": "forward", "Achird": "friendly", "Zubenelgenubi": "casual",
    "Vindemiatrix": "gentle", "Sadachbia": "lively", "Sadaltager": "knowledgeable",
    "Sulafat": "warm",
}

# Ported from SAMPLE_PLAYER/Emotions.kt, thirty eight of them, unchanged.
#
# Why a list at all, when the direction is read as prose and anything would
# work: A FREE TEXT BOX IS A BLANK PAGE, and a blank page in the middle of
# choosing a voice is the moment somebody gives up and takes the default.
#
# The glyph is one character so a direction can be found by shape before it is
# read, and nothing here is an emoji: a monospace grid of them is a mess of
# different widths and half of them are the same yellow circle at this size.
#
# group, label, glyph, the direction itself, what a preview says
EMOTIONS = [
    ["Plain", "Neutral", "—", "even and unhurried, no particular emotion", "is speaking plainly"],
    ["Plain", "Clear", "▭", "clear and articulate, like reading a notice aloud", "is reading this clearly"],
    ["Plain", "Conversational", "◇", "relaxed and conversational, as if talking to a friend", "is just talking"],
    ["Plain", "Narration", "▤", "steady narration, warm but not performed", "is narrating"],
    ["Warm", "Kind", "♡", "gentle and kind, unhurried", "is being kind"],
    ["Warm", "Affectionate", "❥", "affectionate, a smile in the voice", "is feeling affectionate"],
    ["Warm", "Reassuring", "◠", "calm and reassuring, steadying someone", "is reassuring you"],
    ["Warm", "Grateful", "✿", "quietly grateful, sincere", "is grateful"],
    ["Warm", "Tender", "◡", "tender and low, almost private", "is being tender"],
    ["Bright", "Happy", "☀", "genuinely happy, light and quick", "is happy"],
    ["Bright", "Excited", "⚡", "excited, can hardly get the words out fast enough", "is excited"],
    ["Bright", "Playful", "◔", "playful and teasing", "is being playful"],
    ["Bright", "Amused", "≈", "amused, on the edge of laughing", "is amused"],
    ["Bright", "Triumphant", "▲", "triumphant, delighted with itself", "is triumphant"],
    ["Low", "Sad", "▽", "sad and quiet, slowing at the ends of phrases", "is sad"],
    ["Low", "Grieving", "☂", "grieving, barely holding the voice together", "is grieving"],
    ["Low", "Weary", "…", "weary, worn out, no energy left for emphasis", "is exhausted"],
    ["Low", "Disappointed", "↓", "disappointed, flat where it should have lifted", "is disappointed"],
    ["Low", "Regretful", "◟", "regretful, admitting something", "is full of regret"],
    ["Sharp", "Angry", "✖", "angry, clipped and hard on the consonants", "is angry"],
    ["Sharp", "Furious", "‼", "furious, barely holding it together", "is furious"],
    ["Sharp", "Firm", "▮", "firm and final, leaving no room to argue", "is being firm"],
    ["Sharp", "Impatient", "»", "impatient, pushing to get to the end", "is impatient"],
    ["Sharp", "Sarcastic", "¬", "dry and sarcastic, meaning the opposite", "is being sarcastic"],
    ["Tense", "Anxious", "◌", "anxious, breath high and shallow", "is anxious"],
    ["Tense", "Afraid", "△", "afraid, voice unsteady", "is afraid"],
    ["Tense", "Urgent", "!", "urgent, needs to be understood immediately", "is in a hurry"],
    ["Tense", "Suspicious", "◐", "suspicious, weighing every word", "is suspicious"],
    ["Tense", "Whispered", "◦", "whispered, as if someone might hear", "is whispering"],
    ["Still", "Calm", "○", "calm and slow, plenty of space between phrases", "is calm"],
    ["Still", "Meditative", "◎", "meditative, soft, guiding a breath", "is meditating"],
    ["Still", "Reverent", "†", "reverent, careful with the words", "is being reverent"],
    ["Still", "Sleepy", "☾", "quiet and drowsy, winding down", "is falling asleep"],
    ["Work", "Announcer", "◉", "confident announcer, projecting to a room", "is announcing"],
    ["Work", "Documentary", "▦", "measured documentary narration, authoritative", "is narrating a documentary"],
    ["Work", "Teaching", "✎", "explaining patiently to someone learning", "is teaching"],
    ["Work", "Advertising", "★", "upbeat and persuasive, selling something", "is selling something"],
    ["Work", "Storytelling", "❦", "telling a story to a child, colours in the voice", "is telling a story"],
]

PACES = [("normal", ""), ("slow", "slowly"), ("fast", "quickly"),
         ("very slow", "very slowly, with space between the phrases")]


# ------------------------------------------------------------ THE CACHE
#
# A preview is the same request every time: the same voice, the same direction,
# the same fixed sentence. So the second person to press play on "angry" is
# asking a question that has already been answered, and answering it again costs
# one of ten requests that account has for the day.
#
# The key is the sha of the exact prompt and voice that were sent. Not of the
# label — the label is a name for a direction, and if that direction's WORDS are
# ever edited the audio must not still come back from the old key. Hashing what
# was actually sent makes the invalidation automatic and impossible to forget.
#
# It never expires. The same input gives the same output, so there is nothing
# for time to change.
PREVIEW_MODEL = "gemini-2.5-flash-preview-tts"


def preview_line(voice, label):
    """SAMPLE_PLAYER/Emotions.kt: the voice's own name and what it is doing.

    Short on purpose. Auditioning a voice across eight emotions is eight calls,
    and a long sentence makes that a minute of waiting to hear four seconds of
    difference. The name is in it so it is obvious which voice you are hearing."""
    for group, lab, glyph, text, spoken in EMOTIONS:
        if lab.lower() == (label or "").strip().lower():
            return "%s %s." % (voice, spoken)
    return "%s is speaking." % voice


def preview_key(voice, label):
    prompt, _, _ = compile_script("<PREVIEW: %s> %s" % (label, preview_line(voice, label)),
                                  [{"name": "PREVIEW", "voice": voice}])
    h = hashlib.sha256(("%s|%s|%s" % (PREVIEW_MODEL, voice, prompt)).encode()).hexdigest()[:20]
    return h, prompt


def preview_path(h):
    for ext in (".wav", ".mp3"):
        p = os.path.join(PREVIEWS, h + ext)
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            return p
    return None


def preview(voice, label):
    """Cached, and it says which it was. A preview that quietly spends a request
    looks free, and the person finds out at the daily wall."""
    h, prompt = preview_key(voice, label)
    hit = preview_path(h)
    if hit:
        return {"ok": True, "file": os.path.basename(hit), "cached": True,
                "line": preview_line(voice, label)}

    def payload(_m):
        return {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig":
                    {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}

    r = with_fallback([PREVIEW_MODEL] + [m for m in TTS_CHAIN if m != PREVIEW_MODEL], payload)
    if not r["ok"]:
        return r
    pcm = None
    for c in r["data"].get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            if "inlineData" in p:
                pcm = base64.b64decode(p["inlineData"]["data"])
    if not pcm:
        return {"ok": False, "error": "no audio in the reply"}
    os.makedirs(PREVIEWS, exist_ok=True)
    tmp = os.path.join(PREVIEWS, h + ".wav.new")
    secs = pcm_to_wav(tmp, pcm)
    os.replace(tmp, os.path.join(PREVIEWS, h + ".wav"))
    spend(r["label"], r["model"], n=0, audio_out=secs)
    return {"ok": True, "file": h + ".wav", "cached": False, "seconds": round(secs, 1),
            "key": r["label"], "line": preview_line(voice, label)}


def cache_state():
    n, b = 0, 0
    if os.path.isdir(PREVIEWS):
        for f in os.listdir(PREVIEWS):
            if f.endswith((".wav", ".mp3")):
                n += 1
                b += os.path.getsize(os.path.join(PREVIEWS, f))
    return {"count": n, "bytes": b}


def emotion_by_label(label):
    want = (label or "").strip().lower()
    for group, lab, glyph, text, spoken in EMOTIONS:
        if lab.lower() == want:
            return text
    return ""


TAG_RE = re.compile(r"<\s*([^<>:|]{1,30}?)\s*(?::\s*([^<>:|]{0,40}?))?\s*(?::\s*([^<>|]{0,30}?))?\s*>")


def compile_script(text, speakers):
    """Turn a tagged script into what Gemini is actually sent.

    THE TAG, invented here because Gemini has nothing like Hume's per-utterance
    `description` field. Hume takes an acting direction beside every line. Gemini
    takes ONE prose direction for the whole call, and a speaker name in front of
    each line. So the tags are compiled rather than passed through.

        <Viveka>                  this line is Viveka's
        <Viveka: Weary>           and he is weary
        <Viveka: Weary: slow>     and slow with it
        <Manan>                   now Manan

    Angle brackets because they cannot be typed by accident in dialogue the way a
    bracket or a slash can, and because the person is already reading a script
    where a name means a speaker.

    Returns (prompt, speakers_used, problems). PROBLEMS ARE NEVER SILENT: a tag
    naming somebody with no voice would otherwise come back as a line read in the
    wrong voice, which sounds like a bad model rather than a typo.
    """
    names = [s.get("name", "").strip() for s in speakers if s.get("name", "").strip()]
    known = {n.lower(): n for n in names}
    problems = []
    lines = []
    cur = names[0] if names else ""
    pending = ""
    pos = 0
    for m in TAG_RE.finditer(text or ""):
        chunk = (text[pos:m.start()] or "").strip()
        if chunk:
            lines.append((cur, pending, chunk))
            pending = ""
        who = (m.group(1) or "").strip()
        if who.lower() in known:
            cur = known[who.lower()]
        else:
            problems.append("no voice is set for <%s>" % who)
        emo = (m.group(2) or "").strip()
        pace = (m.group(3) or "").strip()
        bits = []
        if emo:
            d = emotion_by_label(emo)
            if not d:
                problems.append("no direction called %s" % emo)
            bits.append(d or emo)
        if pace:
            p = dict(PACES).get(pace.lower(), pace)
            if p:
                bits.append(p)
        pending = ", ".join(bits)
        pos = m.end()
    tail = (text[pos:] or "").strip()
    if tail:
        lines.append((cur, pending, tail))

    used = [n for n in names if any(l[0] == n for l in lines)] or names[:1]
    if len(used) > 2:
        problems.append("Gemini takes two speakers in one call and this has %d" % len(used))
        used = used[:2]

    head = []
    if len(used) > 1:
        head.append("TTS the following conversation between %s." % " and ".join(used))
    else:
        head.append("Read the following aloud.")
    for s in speakers:
        n = s.get("name", "").strip()
        if n in used:
            head.append("%s is a %s voice."
                        % (n, VOICE_TIMBRE.get(s.get("voice", ""), "clear")))
    head.append("Follow the direction in brackets before each line "
                "and do not read the brackets aloud.")

    body = []
    for who, direction, said in lines:
        prefix = ("%s: " % who) if len(used) > 1 else ""
        body.append(prefix + (("(%s) " % direction) if direction else "") + said)
    return "\n".join(head) + "\n\n" + "\n".join(body), used, problems


def speak(text, voice, voice2=None, name_a="A", name_b="B"):
    def payload(_model):
        if voice2:
            sc = {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
                {"speaker": name_a, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
                {"speaker": name_b, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice2}}}]}}
        else:
            sc = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}
        return {"contents": [{"parts": [{"text": text}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": sc}}

    r = with_fallback(TTS_CHAIN, payload)
    if not r["ok"]:
        return r
    pcm = None
    for c in r["data"].get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            if "inlineData" in p:
                pcm = base64.b64decode(p["inlineData"]["data"])
    if not pcm:
        return {"ok": False, "error": "no audio in the reply", "log": r["log"]}
    os.makedirs(OUTDIR, exist_ok=True)
    fname = "speak_%s.wav" % time.strftime("%Y%m%d_%H%M%S")
    secs = pcm_to_wav(os.path.join(OUTDIR, fname), pcm)
    spend(r["label"], r["model"], n=0, audio_out=secs)
    return {"ok": True, "file": fname, "seconds": round(secs, 1),
            "voice": voice, "model": r["model"], "key": r["label"], "log": r["log"]}


# ------------------------------------------------------------------ LISTEN

MIME = {".mp3": "audio/mp3", ".wav": "audio/wav", ".flac": "audio/flac",
        ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".aac": "audio/aac",
        ".aiff": "audio/aiff"}


def have_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def to_supported(path):
    """Gemini takes wav mp3 flac ogg aac aiff. Anything else, and anything the
    browser recorded, goes through ffmpeg. Mono 16k flac keeps it small."""
    ext = os.path.splitext(path)[1].lower()
    if ext in MIME and ext != ".wav":
        return path, MIME[ext], 0
    if not have_ffmpeg():
        if ext in MIME:
            return path, MIME[ext], 0
        return None, None, 0
    out = tempfile.mktemp(suffix=".flac")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path,
                    "-ar", "16000", "-ac", "1", "-map", "0:a", "-c:a", "flac", out],
                   capture_output=True, timeout=600)
    if not os.path.exists(out):
        return None, None, 0
    secs = 0.0
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", out],
                           capture_output=True, timeout=60)
        secs = float(p.stdout.decode().strip() or 0)
    except Exception:
        pass
    return out, "audio/flac", secs


def listen(path, language="", verbatim=True):
    conv, mime, secs = to_supported(path)
    if not conv:
        return {"ok": False, "error": "cannot read that file, and no ffmpeg to convert it"}
    b = base64.b64encode(open(conv, "rb").read()).decode()
    ask = "Transcribe this audio. Output only the transcript, nothing else."
    if verbatim:
        ask += " Keep it verbatim, including false starts."
    if language:
        ask += " The language is %s." % language

    def payload(_m):
        return {"contents": [{"parts": [{"text": ask},
                                        {"inlineData": {"mimeType": mime, "data": b}}]}]}

    r = with_fallback(STT_CHAIN, payload)
    if not r["ok"]:
        return r
    text = "".join(p.get("text", "") for c in r["data"].get("candidates", [])
                   for p in c.get("content", {}).get("parts", []))
    um = r["data"].get("usageMetadata", {})
    audio_tokens = 0
    for det in um.get("promptTokensDetails", []):
        if det.get("modality") == "AUDIO":
            audio_tokens = det.get("tokenCount", 0)
    heard = audio_tokens / 25.0 if audio_tokens else secs   # 25 tokens a second, measured
    spend(r["label"], r["model"], n=0, audio_in=heard)
    return {"ok": True, "text": text.strip(), "seconds": round(heard, 1),
            "model": r["model"], "key": r["label"], "log": r["log"]}


# -------------------------------------------------------------------- KEYS

# A key is one of five things and they are not interchangeable. Calling "no
# credit" working sends the ring at a wall; calling it refused has somebody
# delete a live account they only needed to top up. Ported from
# modules/keyring.md 2d and 2e, including the order the tests run in.
#
#   working   it did the work                       use it
#   busy      throttled this minute                 wait, NEVER delete
#   no credit real key, live account, no money      top up, or delete on purpose
#   refused   wrong, revoked, wrong provider        delete
#   unknown   the answer says nothing about the key  try again, never delete
RETRY_HINT = re.compile(r"retrydelay|retry-after|retryinfo|quotafailure|"
                        r"per minute|try again in", re.I)
MONEY_STRONG = re.compile(r"credit|balance|depleted|insufficient|billing|"
                          r"payment|prepayment|e0300|zero_credits", re.I)


WHY = {"working": "valid, and it did real work",
       "busy": "throttled right now, which says nothing about the key",
       "no credit": "the account is alive and has no money in it",
       "refused": "revoked, mistyped, or not a Gemini key",
       "unknown": "no answer about the key itself, try again"}


def verdict_for(code, body):
    """The provider's answer, in one word. A pure function, so it can be tested
    without a key and without a network."""
    b = body if isinstance(body, str) else ""
    if code == 200:
        return "working"
    if code in (401, 403):
        return "refused"
    if code == 429:
        # THE RETRY HINT IS CHECKED FIRST AND WINS. Google answers a spent
        # account and an impatient one with the same status and the same word,
        # so matching on "quota" alone tells somebody to delete a live key
        # because they pressed Test twice in one second.
        if RETRY_HINT.search(b):
            return "busy"
        if MONEY_STRONG.search(b):
            return "no credit"
        return "busy"
    if code == 404:
        return "unknown"          # the model is gone, which says nothing about the key
    if code in (500, 502, 503, 504) or code < 0:
        return "unknown"
    return "unknown"


DELETABLE = ("refused",)          # and "no credit", but only when asked by name


def remove_keys(labels, reason="removed"):
    """Take keys out of the ring and put them where they can be fetched back.

    A permanent condemnation that cannot be undone is a bug wearing a rule's
    clothing, so nothing is destroyed: the entries move to a graveyard file,
    also chmod 600, and Put back returns them. The ring is rewritten whole here
    rather than appended to, which is the one operation that has to be, and it
    goes through a .new file and a rename like everything else."""
    ring = load_ring()
    keep = [(l, k) for l, k in ring if l not in labels]
    gone = [(l, k) for l, k in ring if l in labels]
    if not gone:
        return {"ok": True, "removed": [], "ring": len(ring)}
    head = ""
    if os.path.exists(KEYFILE):
        for line in open(KEYFILE).read().splitlines():
            if line.strip().startswith("#"):
                head += line + "\n"
            elif line.strip():
                break
    body = "".join("%s\n%s\n\n" % (l, k) for l, k in keep)
    tmp = KEYFILE + ".new"
    with open(tmp, "w") as f:
        f.write((head + "\n" if head else "") + body)
    os.chmod(tmp, 0o600)
    os.replace(tmp, KEYFILE)
    os.chmod(KEYFILE, 0o600)

    os.makedirs(HOME, exist_ok=True)
    with open(GRAVEYARD, "a") as f:
        for l, k in gone:
            f.write("# %s, %s\n%s\n%s\n\n" % (reason, time.strftime("%d.%m.%Y %H:%M"), l, k))
    os.chmod(GRAVEYARD, 0o600)
    return {"ok": True, "removed": [{"label": l, "masked": mask(k)} for l, k in gone],
            "ring": len(load_ring())}


def removed_keys():
    if not os.path.exists(GRAVEYARD):
        return []
    lines = [l.rstrip() for l in open(GRAVEYARD).read().splitlines()]
    out, i = [], 0
    while i < len(lines) - 1:
        if lines[i] and not lines[i].startswith("#") and KEY_RE.fullmatch(lines[i + 1].strip()):
            out.append((lines[i], lines[i + 1].strip()))
            i += 2
        else:
            i += 1
    return out


def restore_keys():
    """Put everything back and empty the graveyard. import_keys does the
    merging, so a key that is somehow already in the ring is not doubled."""
    gone = removed_keys()
    if not gone:
        return {"ok": True, "restored": [], "ring": len(load_ring())}
    text = "".join("%s\n%s\n\n" % (l, k) for l, k in gone)
    r = import_keys(text, "put back")
    open(GRAVEYARD, "w").close()
    return {"ok": True, "restored": r["added"], "ring": r["ring"]}


def health():
    """What is installed and what is not. The Keys tab shows this so a missing
    ffmpeg is discovered here rather than by a transcription that fails."""
    import shutil
    def mod(name):
        try:
            __import__(name)
            return True
        except Exception:
            return False
    return {"python": "%d.%d.%d" % sys.version_info[:3],
            "flask": mod("flask"),
            "waitress": mod("waitress"),
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "keyfile": KEYFILE,
            "keys": len(load_ring()),
            "outdir": OUTDIR,
            "version": VERSION}


def test_all_keys():
    """One real call per key, the cheapest model with the most daily room.

    modules/gemini.md: a GET on /models returns 200 for an account with zero
    credit, so it tests validity only. The only way to learn whether an account
    can do work is to ask it to do some."""
    ring = load_ring()
    rows, lock = [], threading.Lock()

    def check(pair):
        label, key = pair
        t0 = time.time()
        code, body = post("gemini-3.1-flash-lite", "generateContent",
                          {"contents": [{"parts": [{"text": "hi"}]}]}, key, timeout=60)
        if code in (503, 500, 502, 504):
            time.sleep(2)                     # busy model, not a bad key
            code, body = post("gemini-3.1-flash-lite", "generateContent",
                              {"contents": [{"parts": [{"text": "hi"}]}]}, key, timeout=60)
        ms = int((time.time() - t0) * 1000)
        v = verdict_for(code, body if isinstance(body, str) else "")
        why = WHY[v]
        if v == "working":
            spend(label, "gemini-3.1-flash-lite")
        elif v == "no credit":
            mark_dead(label, "no credit")
        elif v == "refused":
            mark_dead(label, "refused")
        elif v == "busy":
            q = read_quota(body if isinstance(body, str) else "")
            if q.get("rpd"):
                why = "at its daily wall on this model (%d a day)" % q["rpd"]
        with lock:
            rows.append({"label": label, "masked": mask(key), "verdict": v,
                         "why": why, "ms": ms, "code": code})

    ts = [threading.Thread(target=check, args=(p,)) for p in ring]
    for th in ts:
        th.start()
    for th in ts:
        th.join()
    order = {"working": 0, "busy": 1, "no credit": 2, "unknown": 3, "refused": 4}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), r["label"]))
    return rows


def test_one_key(label):
    """Test a single account. The Key Tester puts test on every row, because
    the question is usually about one account and retesting twenty to answer it
    spends nineteen requests for nothing."""
    for l, key in load_ring():
        if l != label:
            continue
        t0 = time.time()
        code, body = post("gemini-3.1-flash-lite", "generateContent",
                          {"contents": [{"parts": [{"text": "hi"}]}]}, key, timeout=60)
        v = verdict_for(code, body if isinstance(body, str) else "")
        if v == "working":
            spend(label, "gemini-3.1-flash-lite")
        return {"ok": True, "label": label, "masked": mask(key), "verdict": v,
                "why": WHY[v], "ms": int((time.time() - t0) * 1000), "code": code}
    return {"ok": False, "error": "no account called %r" % label}


def models_for(label):
    """What this account can reach. GET /models answers 200 for an account with
    zero credit, so this says nothing about money — it is the catalogue, and it
    is worth seeing when a model name stops working."""
    for l, key in load_ring():
        if l != label:
            continue
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
            headers={"x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return {"ok": False, "error": "the account answered %d" % e.code}
        except Exception as ex:
            return {"ok": False, "error": str(ex)[:120]}
        names = [m["name"].replace("models/", "") for m in d.get("models", [])]
        return {"ok": True, "label": label, "count": len(names),
                "tts": [n for n in names if "tts" in n],
                "image": [n for n in names if "image" in n or "banana" in n],
                "text": [n for n in names if "flash" in n or "pro" in n or "gemma" in n][:14],
                "all": names}
    return {"ok": False, "error": "no account called %r" % label}


REWRITE_PROMPTS = {
    "grammar": ("Correct only the grammar, spelling and punctuation of the text below. "
                "Do not rephrase, do not rearrange or merge sentences, do not change the "
                "wording, structure or shape of the text in any way. Make only the smallest "
                "necessary fixes. Keep the original language. Reply with the corrected text "
                "only, nothing else.\n\nText:\n"),
    "reshape": ("Rewrite the text below so it flows well. Remove every repetition and merge "
                "everything into one clear text that explains the whole message. You may "
                "rearrange sentences freely. Write exactly as a human would. Do not use "
                "dashes, bullet points, headings or any special formatting, only plain "
                "sentences with normal punctuation. Keep the length balanced and the tone "
                "friendly but clear. Keep the original language. Reply with the rewritten "
                "text only, nothing else.\n\nText:\n"),
}


def rewrite(kind, text):
    """Correct or reshape a transcript. THE MODEL IS NOT A SETTING.

    modules/model-names.md: a dated model string is a time bomb — it fails with
    not_found before the request runs, so it never appears in usage and looks
    exactly like a dead key. So there is no model picker and no dated name in
    the page: the chain here is tried in order and the first one that answers
    wins, exactly as Speak and Listen already work."""
    prompt = REWRITE_PROMPTS.get(kind, REWRITE_PROMPTS["grammar"]) + (text or "")

    def payload(_m):
        return {"contents": [{"parts": [{"text": prompt}]}]}

    r = with_fallback(STT_CHAIN, payload)
    if not r["ok"]:
        return r
    out = "".join(p.get("text", "") for c in r["data"].get("candidates", [])
                  for p in c.get("content", {}).get("parts", []))
    return {"ok": True, "text": out.strip(), "model": r["model"], "key": r["label"]}


def budget():
    """What is left today, in requests and in hours."""
    d = read_ledger()
    ring = [(l, k) for l, k in load_ring() if l not in d["dead"]]
    out = {"keys_live": len(ring), "models": [], "day": d["day"],
           "reset_in": seconds_to_reset(),
           "audio_out": round(d["audio_out"], 1), "audio_in": round(d["audio_in"], 1)}
    for model, meta in LIMITS.items():
        cap = limit_for(model, "rpd")
        used = sum(v for k, v in d["spend"].items() if k.endswith("|" + model))
        total = cap * len(ring)
        out["models"].append({
            "model": model, "use": meta["use"], "rpm": limit_for(model, "rpm"),
            "rpd": cap, "measured": meta["rpd"] is not None,
            "total": total, "used": used, "left": max(total - used, 0)})
    out["ledger_only"] = True   # counts what this app spent, not what other tools spent
    tts_left = sum(m["left"] for m in out["models"] if m["use"] == "tts")
    stt_left = sum(m["left"] for m in out["models"] if m["use"] == "stt")
    # 8 minutes is the measured per-request ceiling; 2 minutes is a normal take
    out["speak_hours_max"] = round(tts_left * 8 / 60.0, 1)
    out["speak_hours_real"] = round(tts_left * 2 / 60.0, 1)
    # one STT call can hold about 11 hours of audio in a 1M context window
    out["listen_hours_max"] = round(stt_left * 11, 1)
    out["listen_hours_real"] = round(stt_left * 0.25, 1)
    return out


# ------------------------------------------------------------------- tests

def run_tests():
    print("GOOGLE TTS AND STT v%d, four tests, real keys" % VERSION)

    # Running four provider tests against an empty ring produces four failures
    # that all mean one thing, and none of them says what that thing is. Say it
    # once, here, and stop.
    if not load_ring():
        print("\n  The key ring is empty, so there is nothing to test.")
        print("  %s holds no keys." % KEYFILE)
        print("\n  Give it your key file, in whatever shape it was saved:")
        print("      gtt import /sdcard/Download/your-keys.txt")
        print("\n  A note, a .env, a JSON export, a CSV, a markdown table: it")
        print("  finds the keys itself and never adds one twice.\n")
        return 1

    ok = 0
    print("1. key ring parses and at least one key is live")
    rows = test_all_keys()
    live = [r for r in rows if r["verdict"] in ("working", "busy")]
    for r in rows:
        print("   %-14s %-9s %s" % (r["label"], r["verdict"], r["why"]))
    print("   %d live of %d" % (len(live), len(rows)))
    ok += 1 if live else 0

    print("2. Speak makes audio")
    r = speak("Say plainly: the fuel is still there.", "Charon")
    if r.get("ok"):
        print("   %s  %.1fs  via %s on [%s]" % (r["file"], r["seconds"], r["model"], r["key"]))
    else:
        print("   FAILED %s %s" % (r.get("error"), r.get("log")))
    ok += 1 if r.get("ok") and r["seconds"] > 0.5 else 0

    print("3. Listen reads that audio back")
    t = {}
    if r.get("ok"):
        t = listen(os.path.join(OUTDIR, r["file"]))
        if t.get("ok"):
            print("   heard: %r via %s on [%s]" % (t["text"][:60], t["model"], t["key"]))
        else:
            print("   FAILED %s %s" % (t.get("error"), t.get("log")))
    ok += 1 if t.get("ok") and "fuel" in t.get("text", "").lower() else 0

    print("4. the ledger counted it and knows when it resets")
    b = budget()
    h = b["reset_in"] // 3600
    print("   day %s, resets in %dh%02dm" % (b["day"], h, (b["reset_in"] % 3600) // 60))
    for m in b["models"]:
        star = "" if m["measured"] else "  (rpd assumed, never reached)"
        print("   %-30s %4d of %4d left today%s" % (m["model"], m["left"], m["total"], star))
    print("   speak: up to %.1f h today, realistically %.1f h" % (b["speak_hours_max"], b["speak_hours_real"]))
    print("   listen: %d calls left, and one call holds about 11 h of audio" %
          sum(m["left"] for m in b["models"] if m["use"] == "stt"))
    ok += 1 if b["models"] and b["reset_in"] > 0 else 0

    print("\n%d of 4 green" % ok)
    return 0 if ok == 4 else 1


# --------------------------------------------------------------------- web

PAGE = "@@PAGE@@"   # src/15_page.html, inlined by tools/build_installer.py


# =========================================================================
# THE SERVER, ported from MAHA_TRANSCRIBE_TERMUX_TERMINAL
#
# Not written fresh. modules/keyring.md's own house rule: read the file that
# already solves a problem before writing a new one, and port it with its
# comments intact. Three files came across - portpick.py, localguard.py and
# console.py - condensed here because this app ships as one file, with the
# reasons kept, because the reasons are what was paid for.
# =========================================================================

MAX_PORT_TRIES = 16          # 7311 through 7326, then the OS decides
GUARD_HEADER = "X-Gtt-Local"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
OPEN_ENDPOINTS = {"index", "out", "favicon_ico", "transcribe_page", "preview_file"}
_SELF_MARKER = b"GOOGLE TTS AND STT"


def port_is_free(host, port, timeout=0.4):
    """Can we actually BIND it? Not "is something listening".

    Asking whether something is listening answers a different question: a
    socket in TIME_WAIT, or bound to another interface, or owned by another
    user, all answer "nothing is listening" and then refuse the bind. The only
    honest test is to try.

    NOT SO_REUSEADDR. With it this test succeeds on a port another process is
    already serving from, and then the server fails behind us.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(timeout)
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def whats_there(port, timeout=1.0):
    """A guess at what holds the port, for the message only. Never raises: a
    diagnosis is not worth failing a startup over."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(("127.0.0.1", int(port)))
            s.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            body = b""
            while len(body) < 4000:
                chunk = s.recv(2048)
                if not chunk:
                    break
                body += chunk
        finally:
            s.close()
        if not body:
            return None
        return "self" if _SELF_MARKER in body else "something"
    except Exception:
        return None


def pick_port(host, preferred, tries=MAX_PORT_TRIES):
    """Find a port. ALWAYS returns one.

    An app that refuses to open because something else is on its port is an app
    that is not there when it is wanted - and the thing on the port is very
    often this app, still running from before, so the launcher would be
    blocking on its own success case.

    What it must NOT do is pick a port and let the rest of the app carry on
    believing the old one. Two things depend on the real number: the browser,
    which opens nothing if it is wrong, and the guard, which checks the Host
    header against it and would refuse every request from the page it just
    opened.
    """
    preferred = int(preferred or 7311)
    if port_is_free(host, preferred):
        return preferred, None
    holder = whats_there(preferred)
    if holder == "self":
        why = "port %d is already used by another copy of this app" % preferred
    elif holder == "something":
        why = "port %d is used by another program" % preferred
    else:
        why = "port %d could not be opened" % preferred
    for p in range(preferred + 1, preferred + tries):
        if port_is_free(host, p):
            return p, "%s, so this one is on %d" % (why, p)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    p = s.getsockname()[1]
    s.close()
    return p, "%s, and so were the fifteen after it, so the system chose %d" % (why, p)


def guard(port):
    """No passwords, and still not open to the internet.

    Any site you have open in another tab can make your browser send requests
    to 127.0.0.1 in the background. This app deletes keys and spends quota, so
    that matters, and binding to loopback does not stop it: Host reflects where
    the browser actually connected, which is correctly 127.0.0.1 even for a
    cross-site fetch from a page you merely have open.

        1  HOST        must be a loopback name. Catches DNS REBINDING, where a
                       site points a hostname at 127.0.0.1 after the fact, so
                       the connection really is local and the browser still
                       sends that site's own Host header.
        2  ORIGIN      if present it must be this app. A browser attaches
                       Origin to every cross-site POST.
        3  OUR HEADER  a header this page always sends and a cross-site
                       request cannot. A form POST cannot set custom headers at
                       all, and a fetch that tries triggers a preflight that
                       never gets an allow.

    A plain page load passes on 1 and 2 alone, because typing the address in
    yourself sends no Origin and no custom header.
    """
    from flask import jsonify, request
    host = request.headers.get("Host", "")
    h = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    if h.startswith("[") and "]" in h:
        h = h[:h.index("]") + 1]
    if h not in LOCAL_HOSTS:
        return (jsonify({"error": "This app only answers to 127.0.0.1. The address "
                                  "used to reach it was different, which is what a "
                                  "DNS-rebinding attack looks like. Open "
                                  "http://127.0.0.1:%d instead." % port}), 403)
    origin = request.headers.get("Origin") or ""
    if not origin:
        ref = request.headers.get("Referer") or ""
        if ref:
            parts = ref.split("/")
            origin = "/".join(parts[:3]) if len(parts) >= 3 else ""
    if origin:
        allowed = {"http://%s:%d" % (x, port) for x in ("127.0.0.1", "localhost", "[::1]")}
        if origin.rstrip("/") not in allowed:
            return (jsonify({"error": "That request came from another web page, so it "
                                      "was refused. Nothing was changed."}), 403)
    changes = request.method not in SAFE_METHODS
    is_api = (request.path or "").startswith("/api/")
    if (changes or is_api) and request.endpoint not in OPEN_ENDPOINTS:
        if not request.headers.get(GUARD_HEADER):
            return (jsonify({"error": "That request did not come from this app's own "
                                      "page. Nothing was changed."}), 403)
    return None


def quiet_flask():
    """Werkzeug shouts a red block about development servers. Read as broken it
    makes every visit feel like an incident, and this binds to loopback only, so
    the warning's actual concern does not apply."""
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *a, **k: None
    except Exception:
        pass
    try:
        import werkzeug.serving as ws
        ws._log = lambda *a, **k: None
    except Exception:
        pass


# One line at a time, never a box. A panel built to a fixed inner width
# truncates whatever does not fit, and on a forty column phone terminal that
# means most of the key row disappears while still being bound. Plain lines let
# the terminal wrap the way terminals already know how to.
LOGO = [
    " ██████╗ ████████╗████████╗",
    "██╔════╝ ╚══██╔══╝╚══██╔══╝",
    "██║  ███╗   ██║      ██║   ",
    "██║   ██║   ██║      ██║   ",
    "╚██████╔╝   ██║      ██║   ",
    " ╚═════╝    ╚═╝      ╚═╝   ",
]
AMBER, SAND, SLATE, RED, OFF = ("\033[38;5;214m", "\033[38;5;223m",
                                "\033[38;5;245m", "\033[38;5;203m", "\033[0m")


def open_page(url):
    """Open the phone's own browser. webbrowser.open DOES NOT WORK on Termux:
    it looks for desktop browsers and desktop environment variables, finds
    none, returns False and says nothing. So the chain below, in this order.

    `am start` prints its failure and STILL EXITS ZERO - asking for a package
    that is not installed writes "Activity not started, unable to resolve
    Intent" and returns success - so its OUTPUT is read, not its exit code."""
    def run(cmd):
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=15)
            out = (p.stdout + p.stderr).decode("utf-8", "replace").lower()
            if p.returncode != 0 or "unable to resolve" in out or "error" in out:
                return False
            return True
        except Exception:
            return False

    if run(["am", "start", "-a", "android.intent.action.VIEW", "-d", url]):
        return "am start"
    if run(["termux-open-url", url]):
        return "termux-open-url"
    for c in ("xdg-open", "open"):
        if run([c, url]):
            return c
    try:
        import webbrowser
        if webbrowser.open(url):
            return "webbrowser"
    except Exception:
        pass
    return ""


def serve():
    from flask import Flask, request, jsonify, send_from_directory

    app = Flask(__name__)
    live = {"port": PORT}

    @app.before_request
    def gate():
        return guard(live["port"])

    @app.get("/")
    def index():
        return (PAGE.replace("@@ASSUMED@@", str(RPD_UNKNOWN_ASSUMED))
                .replace("@@VERSION@@", "v%d" % VERSION))

    @app.get("/transcribe")
    def transcribe_page():
        """Maha Transcribe, whole. Recording, the queue, the archive, copying,
        correction, translation, the settings: the app as it is. The engine
        behind it is this ring."""
        f = os.path.join(HOME, "transcribe.html")
        if not os.path.exists(f):
            return ("transcribe.html is not installed next to app.py", 404)
        return send_from_directory(HOME, "transcribe.html")

    @app.get("/favicon.ico")
    def favicon_ico():
        return ("", 204)

    @app.get("/out/<path:f>")
    def out(f):
        return send_from_directory(OUTDIR, f)

    @app.post("/api/speak")
    def api_speak():
        j = request.get_json(force=True)
        txt = (j.get("text") or "").strip()
        if not txt:
            return jsonify({"ok": False, "error": "nothing to say"})
        speakers = j.get("speakers") or []
        speakers = [s for s in speakers if (s.get("name") or "").strip()]
        if not speakers:
            speakers = [{"name": "SPEAKER", "voice": j.get("voice") or "Charon"}]
        prompt, used, problems = compile_script(txt, speakers)
        by = {s["name"]: s.get("voice") or "Charon" for s in speakers}
        r = speak(prompt,
                  by.get(used[0], "Charon"),
                  by.get(used[1]) if len(used) > 1 else None,
                  used[0], used[1] if len(used) > 1 else "")
        r["problems"] = problems
        r["prompt"] = prompt
        return jsonify(r)

    @app.get("/preview/<path:f>")
    def preview_file(f):
        return send_from_directory(PREVIEWS, f)

    @app.get("/api/preview")
    def api_preview():
        v = request.args.get("voice") or "Charon"
        e = request.args.get("emotion") or "Neutral"
        if v not in VOICE_TIMBRE:
            return jsonify({"ok": False, "error": "no voice called %r" % v})
        return jsonify(preview(v, e))

    @app.get("/api/cache")
    def api_cache():
        return jsonify(cache_state())

    @app.get("/api/voices")
    def api_voices():
        return jsonify([{"name": n, "timbre": VOICE_TIMBRE[n]} for n in sorted(VOICE_TIMBRE)])

    @app.get("/api/emotions")
    def api_emotions():
        return jsonify([{"group": g, "label": l, "glyph": gl, "text": tx, "spoken": sp}
                        for g, l, gl, tx, sp in EMOTIONS])

    @app.post("/api/listen")
    def api_listen():
        f = request.files.get("audio")
        if not f:
            return jsonify({"ok": False, "error": "no file"})
        p = tempfile.mktemp(suffix=os.path.splitext(f.filename or "a.wav")[1] or ".wav")
        f.save(p)
        try:
            return jsonify(listen(p, (request.form.get("lang") or "").strip()))
        finally:
            try:
                os.remove(p)
            except Exception:
                pass

    @app.post("/api/import")
    def api_import():
        f = request.files.get("keyfile")
        if not f:
            return jsonify({"ok": False, "error": "no file"})
        raw = f.read(MAX_IMPORT_BYTES + 1)
        if len(raw) > MAX_IMPORT_BYTES:
            return jsonify({"ok": False, "error": "that file is over 8 MB, which is not a key file"})
        return jsonify(import_keys(raw.decode("utf-8", "replace"), f.filename or "a file"))

    @app.post("/api/rewrite")
    def api_rewrite():
        j = request.get_json(force=True) or {}
        txt = (j.get("text") or "").strip()
        if not txt:
            return jsonify({"ok": False, "error": "nothing to rewrite"})
        return jsonify(rewrite(j.get("kind") or "grammar", txt))

    @app.get("/api/health")
    def api_health():
        return jsonify(health())

    @app.get("/api/keys")
    def api_keys():
        return jsonify(test_all_keys())

    @app.get("/api/ring")
    def api_ring():
        """The accounts, with no verdicts. Drawn first so the rows exist before
        the testing starts: nothing appears, nothing disappears, things become
        active. Twenty rows arriving one at a time is a page that jumps."""
        return jsonify({"keys": [{"label": l, "masked": mask(k)} for l, k in load_ring()]})

    @app.post("/api/key/<path:label>/test")
    def api_key_test(label):
        return jsonify(test_one_key(label))

    @app.get("/api/key/<path:label>/models")
    def api_key_models(label):
        return jsonify(models_for(label))

    @app.post("/api/delete")
    def api_delete():
        j = request.get_json(force=True) or {}
        labels = [str(x) for x in (j.get("labels") or [])]
        if not labels:
            return jsonify({"ok": False, "error": "nothing named"})
        return jsonify(remove_keys(labels, "refused"))

    @app.get("/api/removed")
    def api_removed():
        g = removed_keys()
        return jsonify({"count": len(g),
                        "keys": [{"label": l, "masked": mask(k)} for l, k in g]})

    @app.post("/api/restore")
    def api_restore():
        return jsonify(restore_keys())

    @app.get("/api/budget")
    def api_budget():
        return jsonify(budget())

    os.makedirs(OUTDIR, exist_ok=True)
    quiet_flask()

    # The port ACTUALLY bound, which is not always the one asked for. Set once
    # and read from here everywhere downstream, so no part of the app can be
    # left believing the wrong number.
    port, note = pick_port("127.0.0.1", PORT)
    live["port"] = port
    url = "http://127.0.0.1:%d" % port
    ring = load_ring()
    colour = sys.stdout.isatty()

    def w(s, c):
        return (c + s + OFF) if colour else s

    print("")
    for row in LOGO:
        print("  " + w(row, AMBER))
    print("")
    print("  " + w("Google TTS and STT", SAND) + "   \u00b7   " + w(url, SLATE))
    print("  " + w("v%d" % VERSION, SLATE) + "   \u00b7   " +
          w("%d account%s" % (len(ring), "" if len(ring) == 1 else "s"), SLATE))
    if note:
        print("  " + w(note, SAND))
    if not ring:
        # An empty ring is not a reason to refuse to start. The picker that
        # fixes it is ON THE PAGE, so refusing to open the page is refusing to
        # let anybody fix it.
        print("  " + w("no keys yet \u2014 the KEYS tab has a file picker", SAND))
    print("")

    threading.Thread(target=lambda: app.run(host="127.0.0.1", port=port, threaded=True,
                                            debug=False, use_reloader=False),
                     daemon=True).start()

    def kick():
        time.sleep(1.0)
        how = open_page(url)
        if not how:
            print("  " + w("no way to open a browser from here, go to %s yourself" % url, RED))
    threading.Thread(target=kick, daemon=True).start()

    try:
        subprocess.Popen(["termux-wake-lock"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # Plain lines and single keys, never a redrawn box. A panel built to a
    # fixed inner width truncates whatever does not fit, and on a forty column
    # phone terminal that means most of the key row disappears while still
    # being bound. DEGRADES HONESTLY: with no terminal there is no key to
    # press, so it just serves.
    if not (sys.stdout.isatty() and sys.stdin.isatty()):
        print("  serving. ctrl-c to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return

    print("  " + w("q", AMBER) + " quit   " + w("o", AMBER) + " open page   " +
          w("u", AMBER) + " update   " + w("k", AMBER) + " keys   " +
          w("t", AMBER) + " test")
    print("")
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            r, _, _ = select.select([fd], [], [], 0.5)
            if not r:
                continue
            ch = os.read(fd, 1).decode(errors="ignore").lower()
            if ch in ("q", "\x03", "\x04"):
                print("  stopped.")
                break
            if ch == "o":
                print("  " + ("opening the browser" if open_page(url)
                              else w("no way to open a browser from here", RED)))
            if ch == "u":
                # REPLACE THIS PROCESS. Running the updater as a child looked
                # like the installer hanging: it finished, printed "installed",
                # and handed the terminal back to a loop that was still in
                # cbreak, still serving the OLD code on the port, and showing
                # no prompt. Nothing was wrong except that nothing said so.
                #
                # exec ends this copy first. The port is freed, the terminal
                # goes back to the shell when the installer is done, and there
                # is no old version left running to be confused by.
                print("")
                print("  " + w("stopping this copy, then updating.", SAND))
                print("  " + w("run  gtt  again when it finishes.", SAND))
                print("")
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                try:
                    subprocess.Popen(["termux-wake-unlock"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                try:
                    os.execvp("gtt-update", ["gtt-update"])
                except Exception as ex:
                    print("  could not run gtt-update: %s" % ex)
                    tty.setcbreak(fd)
            if ch == "k":
                for l, k in load_ring():
                    print("  %-24s %s" % (l, mask(k)))
                if not load_ring():
                    print("  the ring is empty")
            if ch == "t":
                for row in test_all_keys():
                    print("  %-24s %-10s %s" % (row["label"], row["verdict"], row["why"]))
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        try:
            subprocess.Popen(["termux-wake-unlock"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except Exception:
            pass


def cli_import(path):
    if not os.path.exists(path):
        sys.exit("no file at %s" % path)
    if os.path.getsize(path) > MAX_IMPORT_BYTES:
        sys.exit("that file is over 8 MB, which is not a key file")
    r = import_keys(open(path, "rb").read().decode("utf-8", "replace"), os.path.basename(path))
    print("  %d key(s) found in %s" % (r["found"], r["source"]))
    for a in r["added"]:
        print("  + %-24s %s" % (a["label"], a["masked"]))
    for a in r["duplicates"]:
        print("  = %-24s %s   already in the ring" % (a["label"] or "", a["masked"]))
    for m in r["maybes"]:
        print("  ? %s  not a format I know, left alone" % m)
    print("  the ring now holds %d" % r["ring"])
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        sys.exit(run_tests())
    if len(sys.argv) > 2 and sys.argv[1] == "import":
        sys.exit(cli_import(sys.argv[2]))
    serve()
