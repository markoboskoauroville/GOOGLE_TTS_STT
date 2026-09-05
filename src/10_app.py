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

import base64, json, os, re, subprocess, sys, tempfile, threading, time
import urllib.error, urllib.request, wave
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:
    PACIFIC = timezone(timedelta(hours=-8))

VERSION = 6
PORT = int(os.environ.get("GTTS_PORT", "7311"))
KEYFILE = os.environ.get("GEMINI_KEYS", os.path.expanduser("~/.gemini_keys"))
HOME = os.path.expanduser("~/.google_tts_stt")
LEDGER = os.path.join(HOME, "ledger.json")
GRAVEYARD = os.path.join(HOME, "removed_keys")
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
        why = {"working": "",
               "busy": "throttled right now, this says nothing about the key",
               "no credit": "the account is alive and has no money in it",
               "refused": "revoked, mistyped, or not a Gemini key",
               "unknown": "no answer about the key, try again"}[v]
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

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Google TTS and STT</title><style>
:root{--bg:#0B0D10;--panel:#141A21;--line:#23303D;--ink:#F2DDB4;--mute:#8A9099;--key:#F59E0B;--bad:#EF4444;--ok:#22C55E}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,"Helvetica Neue",Inter,sans-serif;font-variant-numeric:tabular-nums}
.wrap{max-width:720px;margin:0 auto;padding:20px 16px 80px}
h1{font-size:15px;font-weight:500;color:var(--mute);margin:0 0 16px}
h1 b{color:var(--key);font-weight:500}
nav{display:flex;gap:2px;border-bottom:1px solid var(--line);margin-bottom:22px}
nav button{flex:1;background:none;border:0;border-bottom:2px solid transparent;color:var(--mute);font:inherit;padding:11px 4px;cursor:pointer}
nav button.on{color:var(--ink);border-bottom-color:var(--key)}
section{display:none}section.on{display:block}
textarea,input,select{width:100%;background:var(--panel);border:1px solid var(--line);color:var(--ink);font:inherit;padding:11px;border-radius:6px}
textarea{min-height:150px;resize:vertical}
label{display:block;color:var(--mute);font-size:13px;margin:14px 0 5px}
.row{display:flex;gap:10px}.row>*{flex:1}
button.go{width:100%;margin-top:16px;background:var(--key);color:#12181c;border:0;padding:13px;border-radius:6px;font:inherit;font-weight:600;cursor:pointer}
button.go:disabled{opacity:.5}
.out{margin-top:18px;padding:14px;background:var(--panel);border-radius:6px;white-space:pre-wrap;min-height:52px}
.idle{opacity:.38;pointer-events:none}
audio{width:100%;margin-top:12px}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line)}
th{color:var(--mute);font-weight:500}
.working{color:var(--ok)}
.busy{color:var(--key)}
.nocredit{color:var(--key)}
.unknown{color:var(--mute)}
.refused{color:var(--bad)}
button.go.dim{background:var(--panel);color:var(--mute);border:1px solid var(--line)}
button.go.dim:disabled{opacity:.45}
button.go.arm{background:var(--bad);color:#fff;border:0}
.row button.go{margin-top:10px}
.big{font-size:30px;font-weight:300;margin:2px 0}
.note{color:var(--mute);font-size:13px;margin:4px 0 18px}
.bar{height:5px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:5px}
.bar i{display:block;height:100%;background:var(--key)}
</style></head><body><div class="wrap">
<h1>Google TTS and STT &nbsp;<b>v1</b></h1>
<nav>
<button class="on" onclick="tab(0)">Speak</button>
<button onclick="tab(1)">Listen</button>
<button onclick="tab(2)">Keys</button>
</nav>

<section class="on">
<textarea id="text" placeholder="Say warmly and slowly: the arm is always yours. The permission is mine.

Direction goes in the text itself, in plain English. For two speakers, tick the box and write NAME: line."></textarea>
<div class="row">
<div><label>Voice</label><select id="v1"></select></div>
<div><label>Second voice</label><select id="v2"><option value="">none, one speaker</option></select></div>
</div>
<div class="row">
<div><label>First speaker name</label><input id="na" value="VIVEKA"></div>
<div><label>Second speaker name</label><input id="nb" value="MANAN"></div>
</div>
<button class="go" id="sgo" onclick="doSpeak()">Speak</button>
<div class="out idle" id="sout">nothing spoken yet</div>
<audio id="player" class="idle" controls></audio>
</section>

<section>
<label>Audio file</label>
<input type="file" id="file" accept="audio/*">
<div class="row">
<div><label>Language hint</label><input id="lang" placeholder="Croatian, English, leave blank to let it decide"></div>
</div>
<button class="go" id="lgo" onclick="doListen()">Transcribe</button>
<div class="out idle" id="lout">nothing transcribed yet</div>
</section>

<section>
<div id="bud" class="idle">reading the ledger…</div>

<label>Add accounts from a file</label>
<input type="file" id="kf" onchange="doImport()">
<div class="note" id="knote">Any file. A note, a .env, a JSON export, a CSV, a
markdown table. It finds the keys, takes the account names where they are
there, and adds only the ones the ring does not already have.</div>
<div class="out idle" id="kimp">nothing imported this session</div>

<button class="go" onclick="testKeys()">Test every account</button>
<div id="keys" class="out idle">no account tested this session</div>
<div class="row">
<button class="go dim" id="del" onclick="deleteRefused()" disabled>Delete the refused ones</button>
<button class="go dim" id="undel" onclick="putBack()" disabled>Put back</button>
</div>
<div class="note">Refused means revoked, mistyped, or not a Gemini key. A busy
account is never deleted: throttled says nothing about the key. Nothing is
destroyed either way — deleted accounts move to a file and Put back returns
them.</div>
<div id="dep" class="note idle">checking what is installed…</div>
</section>
</div>
<script>
const V=%%VOICES%%;
V.forEach(v=>{v1.add(new Option(v,v));v2.add(new Option(v,v))});
v1.value="Charon";
window.addEventListener('load',loadBudget);
function tab(i){document.querySelectorAll('nav button').forEach((b,j)=>b.classList.toggle('on',i==j));
 document.querySelectorAll('section').forEach((s,j)=>s.classList.toggle('on',i==j));if(i==2){loadBudget();loadHealth();checkGrave();}}
async function doSpeak(){
 sgo.disabled=true;sout.textContent='generating, about half the length of the audio…';
 const r=await(await fetch('/api/speak',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({text:text.value,voice:v1.value,voice2:v2.value,na:na.value,nb:nb.value})})).json();
 sgo.disabled=false;
 sout.classList.remove('idle');
 if(r.ok){sout.textContent=r.seconds+'s of audio, '+r.model+' on key ['+r.key+']'+(r.log.length?'\\n'+r.log.join('\\n'):'');
  player.src='/out/'+r.file;player.classList.remove('idle');}
 else sout.textContent='no: '+r.error+'\\n'+(r.log||[]).join('\\n');}
async function doListen(){
 if(!file.files[0]){lout.textContent='pick a file first';return;}
 lgo.disabled=true;lout.textContent='listening…';
 const fd=new FormData();fd.append('audio',file.files[0]);fd.append('lang',lang.value);
 const r=await(await fetch('/api/listen',{method:'POST',body:fd})).json();
 lgo.disabled=false;lout.classList.remove('idle');
 lout.textContent=r.ok?r.text+'\\n\\n— '+r.seconds+'s heard, '+r.model+' on ['+r.key+']':'no: '+r.error;}
async function loadBudget(){
 const b=await(await fetch('/api/budget')).json();
 const h=Math.floor(b.reset_in/3600),m=Math.floor(b.reset_in%3600/60);
 let s='<div class="big">'+b.speak_hours_real+' h</div><div class="note">of speech left today at a normal take length, '
  +b.speak_hours_max+' h if every call is run to its eight minute ceiling. '
  +b.keys_live+' live keys. Resets in '+h+'h'+m+'m at midnight Pacific.</div>';
 s+='<div class="note">Used so far today: '+b.audio_out+'s made, '+b.audio_in+'s transcribed.</div><table>'
  +'<tr><th>model</th><th>for</th><th>left today</th></tr>';
 b.models.forEach(m=>{const pct=m.total?100*m.left/m.total:0;
  s+='<tr><td>'+m.model+(m.measured?'':' *')+'</td><td>'+m.use+'</td><td>'+m.left+' / '+m.total
   +'<div class="bar"><i style="width:'+pct+'%"></i></div></td></tr>';});
 s+='</table><div class="note">* daily limit never actually reached, so this row is a guess of '+%%ASSUMED%%+' a key.</div>';
 bud.innerHTML=s;bud.classList.remove('idle');}
async function doImport(){
 if(!kf.files[0])return;
 kimp.classList.remove('idle');kimp.textContent='reading '+kf.files[0].name+'…';
 const fd=new FormData();fd.append('keyfile',kf.files[0]);
 const r=await(await fetch('/api/import',{method:'POST',body:fd})).json();
 if(!r.ok){kimp.textContent='no: '+r.error;return;}
 let s=r.found+' key'+(r.found==1?'':'s')+' found in '+r.source+'\\n';
 s+=r.added.length+' added, '+r.duplicates.length+' already in the ring\\n';
 r.added.forEach(a=>{s+='\\n  + '+a.label+'   '+a.masked});
 r.duplicates.forEach(a=>{s+='\\n  = '+(a.label||'already here')+'   '+a.masked});
 if(r.maybes.length)s+='\\n\\nnot a format I know, left alone: '+r.maybes.join(', ');
 s+='\\n\\nthe ring now holds '+r.ring;
 kimp.textContent=s;kf.value='';loadBudget();}
async function loadHealth(){
 const h=await(await fetch('/api/health')).json();
 const y=b=>b?'yes':'no';
 dep.textContent='python '+h.python+' · flask '+y(h.flask)+' · waitress '+y(h.waitress)
  +' · ffmpeg '+y(h.ffmpeg)+' · ring '+h.keys+' accounts at '+h.keyfile;
 dep.classList.remove('idle');}
let REFUSED=[];
async function testKeys(){
 keys.classList.remove('idle');keys.textContent='asking every account to do one small piece of work…';
 const rows=await(await fetch('/api/keys')).json();
 let s='<table><tr><th>account</th><th>key</th><th>answer</th><th>ms</th></tr>';
 REFUSED=[];
 rows.forEach(r=>{
  if(r.verdict=='refused')REFUSED.push(r.label);
  s+='<tr><td>'+r.label+'</td><td>'+r.masked+'</td><td class="'+r.verdict.replace(' ','')+'">'
   +r.verdict+(r.why?'<div class="note" style="margin:0">'+r.why+'</div>':'')+'</td><td>'+r.ms+'</td></tr>';});
 keys.innerHTML=s+'</table>';
 del.disabled=REFUSED.length==0;
 del.textContent=REFUSED.length?('Delete '+REFUSED.length+' refused account'+(REFUSED.length==1?'':'s')):'Delete the refused ones';
 del.className='go '+(REFUSED.length?'arm':'dim');
 loadBudget();checkGrave();}
async function checkGrave(){
 const g=await(await fetch('/api/removed')).json();
 undel.disabled=g.count==0;
 undel.textContent=g.count?('Put back '+g.count):'Put back';}
async function deleteRefused(){
 if(!REFUSED.length)return;
 const r=await(await fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({labels:REFUSED})})).json();
 let s='removed '+r.removed.length+', the ring now holds '+r.ring;
 r.removed.forEach(a=>{s+='\\n  - '+a.label+'   '+a.masked});
 s+='\\n\\nnothing was destroyed. Put back returns them.';
 keys.textContent=s;REFUSED=[];del.disabled=true;del.className='go dim';
 del.textContent='Delete the refused ones';loadBudget();checkGrave();}
async function putBack(){
 const r=await(await fetch('/api/restore',{method:'POST'})).json();
 keys.textContent='put back '+r.restored.length+', the ring now holds '+r.ring;
 loadBudget();checkGrave();}
</script></body></html>"""


def open_page(url):
    """Open the phone's own browser. webbrowser.open DOES NOT WORK on Termux:
    it looks for desktop browsers and desktop environment variables, finds
    none, returns False and says nothing. So the chain below, in this order.

    `am start` prints its failure and STILL EXITS ZERO — asking for a package
    that is not installed writes "Activity not started, unable to resolve
    Intent" and returns success — so its OUTPUT is read, not its exit code."""
    import subprocess
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

    @app.get("/")
    def index():
        return (PAGE.replace("%%VOICES%%", json.dumps(VOICES))
                .replace("%%ASSUMED%%", str(RPD_UNKNOWN_ASSUMED)))

    @app.get("/out/<path:f>")
    def out(f):
        return send_from_directory(OUTDIR, f)

    @app.post("/api/speak")
    def api_speak():
        j = request.get_json(force=True)
        txt = (j.get("text") or "").strip()
        if not txt:
            return jsonify({"ok": False, "error": "nothing to say"})
        v2 = j.get("voice2") or None
        if v2:
            txt = ("TTS the following conversation between %s and %s.\n%s"
                   % (j.get("na", "A"), j.get("nb", "B"), txt))
        return jsonify(speak(txt, j.get("voice") or "Charon", v2,
                             j.get("na", "A"), j.get("nb", "B")))

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

    @app.get("/api/health")
    def api_health():
        return jsonify(health())

    @app.get("/api/keys")
    def api_keys():
        return jsonify(test_all_keys())

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
    url = "http://127.0.0.1:%d" % PORT
    ring = load_ring()

    print("")
    print("  GOOGLE TTS AND STT v%d" % VERSION)
    print("  %s" % url)
    print("  %d account%s in %s" % (len(ring), "" if len(ring) == 1 else "s", KEYFILE))
    if not ring:
        # An empty ring is not a reason to refuse to start. The picker that
        # fixes it is ON THE PAGE, so refusing to open the page is refusing to
        # let anybody fix it. v5 exited here and left the browser unreachable.
        print("  no keys yet — the Keys tab has a file picker, that is where they go")
    print("  ctrl-c to stop")
    print("")

    # 127.0.0.1, not 0.0.0.0. This process holds credentials, and the rule is
    # content binds wide, credentials bind to loopback.
    def kick():
        time.sleep(1.2)
        how = open_page(url)
        print("  browser: %s" % (how or "could not open one, go to %s yourself" % url))
    threading.Thread(target=kick, daemon=True).start()

    try:
        subprocess.Popen(["termux-wake-lock"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception:
        pass

    try:
        from waitress import serve as waitress_serve
        # Waitress, not the Flask development server: single threaded, no
        # request limits, no backpressure, and it says so itself. Waitress is
        # pure python and thread pooled with no compiled extensions, which is
        # why it works in Termux where gunicorn does not.
        waitress_serve(app, host="127.0.0.1", port=PORT, threads=8)
    except ImportError:
        print("  waitress is missing, using the development server")
        app.run(host="127.0.0.1", port=PORT, threaded=True)
    finally:
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
