"""MA-style reading, spoken by Gemini.

The reader from MA Reader Web, with that app's two engines taken out and this
app's one put in. Same page, same gestures, same library; a different voice
behind it and two things it did not have — a direction the voice acts on, and
a word highlight that has to be measured because the engine will not say.

WHAT IS DIFFERENT FROM MA READER WEB, AND WHY

  * The unit key is voice + emotion + pace, not voice. Edge's voice is the
    whole instruction, so its cache key is the voice. Gemini is told how to
    say the line in prose, and the same words read "weary" and read "excited"
    are different audio. Keying on the voice alone would serve a cached calm
    reading of a sentence to somebody who just asked for it furious, once,
    silently, and only for sentences that happened to be cached.

  * THE HIGHLIGHT IS THE SENTENCE, AND ONLY THE SENTENCE. There was a whole
    apparatus here for lighting the individual word being spoken. Gemini
    reports no word times, so each finished clip was sent to a recogniser
    purely as a measuring instrument, and the result aligned onto the visible
    text with Needleman-Wunsch, with a proportional spread underneath for when
    that failed. It worked. It is gone, on purpose.

    It cost a second network call per sentence, a dependency on a provider
    that is not Google, and an answer between 80 and 300 milliseconds out
    depending which instrument happened to be reachable. It bought a marker
    moving inside a sentence that was already lit. The sentence is the unit a
    reader follows, it needs no measurement at all — a clip starts and its
    sentence lights up — and it cannot be out by any milliseconds.

  * No offline export and no second reader yet. Deliberately: the reading has
    to be right before it is worth writing to disk in bulk.
"""

import json
import os
import re
import threading
import time

import voicesex as VSX

HOME = os.path.expanduser("~/.google_tts_stt")
READ_DIR = os.path.join(HOME, "reader")
LIB_DIR = os.path.join(READ_DIR, "library")
STATE_FILE = os.path.join(READ_DIR, "state.json")
STATIC_DIR = os.path.join(HOME, "static")

UNIT_CAP = 320

_locks = {}
_locks_guard = threading.Lock()


def _lock_for(key):
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


# ---------------------------------------------------------------------------
# text: what gets read, and where one sentence stops
# ---------------------------------------------------------------------------
# Ported unchanged from MA Reader Web. It is proven on months of pasted
# articles and every regex in it is a thing that was once read aloud wrongly.

_SENT_RE = re.compile(r"(?<=[.!?…])\s+")
_BLOCK_RE = re.compile(r"\n{2,}")


# AN ORDINAL IS NOT THE END OF A SENTENCE.
#
# "Danas je 8. mjesec" is one sentence, and the plain full-stop rule makes it
# two: "Danas je 8." and "mjesec". Read aloud that is a stop in the middle of
# a date, and it is not rare — it is how every Croatian date is written, and
# how numbered lists and section references are written in English.
#
# The tell is reliable: a full stop after a DIGIT, followed by something that
# does not start a sentence — a lower-case letter, or another digit. A real
# sentence end after a number ("...in 1998. The next year...") is followed by
# a capital, and is left alone.
_ORDINAL_JOIN = re.compile(r"[0-9]\.$")
_STARTS_LOWER = re.compile(r"^[^\W\d_]", re.UNICODE)


def _joins_back(text, left, right):
    if not _ORDINAL_JOIN.search(text[left[0]:left[1]].rstrip()):
        return False
    head = text[right[0]:right[1]].lstrip()[:1]
    if not head:
        return False
    if head.isdigit():
        return True
    return bool(_STARTS_LOWER.match(head)) and head.islower()


def split_sentences(text, lo=0, hi=None):
    if hi is None:
        hi = len(text)
    spans, start = [], lo
    for m in _SENT_RE.finditer(text, lo, hi):
        spans.append((start, m.start()))
        start = m.end()
    if start < hi:
        spans.append((start, hi))
    spans = [(a, b) for a, b in spans if text[a:b].strip()]
    merged = []
    for sp in spans:
        if merged and _joins_back(text, merged[-1], sp):
            merged[-1] = (merged[-1][0], sp[1])
        else:
            merged.append(sp)
    return merged


def split_units(text, cap=UNIT_CAP, blocks=False):
    """Sentences, with anything longer than `cap` broken at a space.

    The cap is not cosmetic. One unit is one synthesis and one clip, and a
    sentence of two thousand characters is a long wait before any sound, a
    large object to hold, and a single clip the highlight has to cross with
    one measurement. Breaking at a space keeps a word whole.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if blocks:
        ranges, start = [], 0
        for m in _BLOCK_RE.finditer(text):
            ranges.append((start, m.start()))
            start = m.end()
        ranges.append((start, len(text)))
        ranges = [(a, b) for a, b in ranges if text[a:b].strip()]
    else:
        ranges = [(0, len(text))]
    units = []
    for ra, rb in ranges:
        for a, b in split_sentences(text, ra, rb):
            s = a
            while b - s > cap:
                cut = text.rfind(" ", s, s + cap)
                if cut <= s:
                    cut = s + cap
                if text[s:cut].strip():
                    units.append((s, cut))
                s = cut
                while s < b and text[s] in " \n\t":
                    s += 1
            if b > s and text[s:b].strip():
                units.append((s, b))
    return units


_FENCE_RE = re.compile(r"^\s*(?:```+|~~~+).*$", re.M)
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_AUTOLINK_RE = re.compile(r"<((?:https?|ftp|mailto):[^>\s]+)>", re.I)
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REFLINK_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_REFDEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+\S.*$", re.M)
_URL_RE = re.compile(r"(?:(?:https?|ftp)://|www\.)[^\s<>)\]}\"']+", re.I)
_MAILTO_RE = re.compile(r"\bmailto:[^\s<>)\]}\"']+", re.I)
_HTML_RE = re.compile(r"</?[A-Za-z][^>]*>")
_CODE_RE = re.compile(r"`+([^`]*)`+")
_EMPH_AST_RE = re.compile(r"(\*\*|\*|~~)(?=\S)(.+?)(?<=\S)\1", re.S)
_EMPH_US_RE = re.compile(r"(?<![\w])(__|_)(?=\S)(.+?)(?<=\S)\1(?![\w])", re.S)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*")
_QUOTE_RE = re.compile(r"^\s{0,3}>+\s?")
_BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+")
_RULE_RE = re.compile(r"^\s{0,3}(?:(?:[-*_]\s*){3,}|=+)\s*$")


def clean_text(text):
    """Only the words. A URL read aloud is a minute of nothing."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _FENCE_RE.sub("", text)
    text = _IMG_RE.sub("", text)
    text = _AUTOLINK_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _REFLINK_RE.sub(r"\1", text)
    text = _REFDEF_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _MAILTO_RE.sub("", text)
    text = _HTML_RE.sub("", text)
    text = _CODE_RE.sub(r"\1", text)
    for _ in range(3):
        new = _EMPH_AST_RE.sub(r"\2", text)
        new = _EMPH_US_RE.sub(r"\2", new)
        if new == text:
            break
        text = new
    out = []
    for ln in text.split("\n"):
        if _RULE_RE.match(ln):
            continue
        ln = _HEADING_RE.sub("", ln)
        ln = _QUOTE_RE.sub("", ln)
        ln = _BULLET_RE.sub(r"\1", ln)
        if "|" in ln:
            stripped = ln.strip()
            if stripped and set(stripped) <= set("|:- "):
                continue
            ln = ln.replace("|", " ")
        out.append(ln)
    text = "\n".join(out)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\[\s*\]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r" *\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# the library
# ---------------------------------------------------------------------------

def _slug(title):
    s = "".join(c if c.isalnum() else "-" for c in (title or "").lower())
    s = re.sub(r"-+", "-", s).strip("-")[:40] or "text"
    return "%s-%d" % (s, int(time.time()))


def lib_save(raw):
    text = clean_text(raw)
    title = (text.strip().splitlines() or ["Untitled"])[0][:64]
    tid = _slug(title)
    d = os.path.join(LIB_DIR, tid)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "text.txt"), "w", encoding="utf-8").write(raw)
    json.dump({"title": title, "created": int(time.time())},
              open(os.path.join(d, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    return tid


def lib_text(tid):
    try:
        return open(os.path.join(LIB_DIR, tid, "text.txt"),
                    encoding="utf-8").read()
    except Exception:
        return ""


def lib_meta(tid):
    try:
        return json.load(open(os.path.join(LIB_DIR, tid, "meta.json"),
                              encoding="utf-8"))
    except Exception:
        return {}


def lib_list():
    out = []
    if not os.path.isdir(LIB_DIR):
        return out
    for tid in os.listdir(LIB_DIR):
        if not os.path.isdir(os.path.join(LIB_DIR, tid)):
            continue
        m = lib_meta(tid)
        txt = lib_text(tid)
        out.append({"id": tid, "title": m.get("title", tid),
                    "created": m.get("created", 0),
                    "chars": len(txt),
                    "units": len(split_units(clean_text(txt)))})
    out.sort(key=lambda r: r.get("created", 0), reverse=True)
    return out


def lib_delete(tid):
    import shutil
    d = os.path.join(LIB_DIR, tid)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


def text_payload(tid):
    """Everything the page needs to render and play a text."""
    text = clean_text(lib_text(tid))
    units = split_units(text)
    m = lib_meta(tid)
    return {"id": tid, "title": m.get("title", "") or
            ((text.strip().splitlines() or ["Untitled"])[0][:64]),
            "sentences": [text[a:b].strip() for a, b in units],
            "count": len(units), "source": lib_text(tid),
            "spoken": text, "spans": [[a, b] for a, b in units]}


# ---------------------------------------------------------------------------
# the voice, the direction, and the key they cache under
# ---------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9]+")


def vkey_for(voice, emotion, pace):
    """One cache key for one way of speaking.

    Voice AND direction AND pace, because all three change the audio. Get this
    wrong in the cheap direction — key on the voice only — and the bug is
    invisible: the right words in the wrong mood, for the sentences that
    happened to be cached already, and never for the ones synthesised fresh.
    """
    return "%s__%s__%s" % (_SAFE.sub("", voice or "Charon") or "Charon",
                           _SAFE.sub("", emotion or "Neutral") or "Neutral",
                           _SAFE.sub("", pace or "normal") or "normal")


def unit_paths(tid, vkey, idx):
    d = os.path.join(LIB_DIR, tid, "audio", vkey)
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, "s%04d" % idx)
    return base + ".wav", base + ".tok.json"


def _direction(app, emotion, pace):
    """The prose Gemini is given instead of a parameter.

    Gemini has no emotion field. It has one prose instruction for the whole
    call, so the choice made in Settings is compiled into a sentence, using
    this app's own table rather than a fresh set of words — the table is
    already tuned and already in the Speak tab, and two vocabularies for one
    idea is how the two drift apart.
    """
    bits = []
    d = app.emotion_by_label(emotion) if emotion else ""
    if d:
        bits.append(d)
    p = dict(app.PACES).get((pace or "").lower(), "")
    if p:
        bits.append(p)
    return ", ".join(bits)


def synth(app, sentence, voice, emotion, pace, wav_path):
    """One sentence into one clip. Returns (seconds, error).

    Deliberately NOT app.speak(). That names its file by the wall clock to the
    second and drops it in the out folder; the reader synthesises three
    sentences ahead, so two clips in the same second would collide and one
    reader would hear the other's sentence. This writes straight to the unit
    path, which is unique by construction.
    """
    direction = _direction(app, emotion, pace)
    head = "Read the following aloud."
    timbre = app.VOICE_TIMBRE.get(voice, "clear")
    head += " The voice is %s." % timbre
    if direction:
        head += (" Read it in this manner: %s."
                 " Do not read this instruction aloud." % direction)
    prompt = head + "\n\n" + sentence

    def payload(_model):
        return {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice}}}}}

    r = app.with_fallback(app.TTS_CHAIN, payload)
    if not r.get("ok"):
        return 0.0, (r.get("error") or "the voice did not answer")
    import base64
    pcm = None
    for c in r["data"].get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            if "inlineData" in p:
                pcm = base64.b64decode(p["inlineData"]["data"])
    if not pcm:
        return 0.0, "no audio in the reply"
    tmp = wav_path + ".part"
    secs = app.pcm_to_wav(tmp, pcm)
    os.replace(tmp, wav_path)
    try:
        app.spend(r["label"], r["model"], n=0, audio_out=secs)
    except Exception:
        pass
    return secs, ""


def ensure_unit(app, tid, vkey, idx, voice, emotion, pace):
    """Clip + timing for one sentence, made once and kept."""
    wav, js = unit_paths(tid, vkey, idx)
    if os.path.isfile(wav) and os.path.isfile(js):
        return wav, js, ""
    with _lock_for((tid, vkey, idx)):
        if os.path.isfile(wav) and os.path.isfile(js):
            return wav, js, ""
        payload = text_payload(tid)
        if idx < 0 or idx >= payload["count"]:
            return None, None, "out of range"
        sentence = payload["sentences"][idx]
        secs, err = synth(app, sentence, voice, emotion, pace, wav)
        if err:
            return None, None, err
        json.dump({"total": round(secs, 3), "sentence": sentence},
                  open(js + ".part", "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(js + ".part", js)
        return wav, js, ""


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

_DEFAULT_STATE = {
    "voice": "Charon", "emotion": "Neutral", "pace": "normal",
    "lang": "eng", "speed": 1.0, "volume": 100, "gap": 0.0, "lag": 0.0,
    "wgap": 0.0, "loop": False, "autoplay": False, "size": 13, "focus": False,
    "theme": "night", "font": "sans", "lineheight": 3, "mode": "read",
    "wordhl": True, "hideTabs": True, "pane": "app",
    "floatPaste": True, "floatFull": True, "floatSwap": True,
    "swapIsPlay": True, "fpX": 0.82, "fpY": 0.72, "ffX": 0.82, "ffY": 0.58,
    "fsX": 0.82, "fsY": 0.44, "fullOnPaste": False, "voiceBar": True,
    # where each of the two voice wheels was left standing
    "vscrollM": 0, "vscrollF": 0,
    "rgbSent": [255, 217, 59], "rgbWord": [226, 59, 78],
    "rgbFont": [255, 255, 255], "rgbText": None,
    "starred": [],
}


def load_state():
    st = dict(_DEFAULT_STATE)
    for path in (STATE_FILE, STATE_FILE + ".bak"):
        try:
            data = json.load(open(path, encoding="utf-8"))
            if isinstance(data, dict):
                st.update(data)
                break
        except Exception:
            continue
    return st


def save_state(d):
    os.makedirs(READ_DIR, exist_ok=True)
    st = load_state()
    if isinstance(d, dict):
        st.update(d)
    try:
        if os.path.exists(STATE_FILE):
            import shutil
            shutil.copyfile(STATE_FILE, STATE_FILE + ".bak")
    except Exception:
        pass
    tmp = STATE_FILE + ".part"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, STATE_FILE)
    return st


# ---------------------------------------------------------------------------
# the routes
# ---------------------------------------------------------------------------

def mount(app_module, flask_app):
    """Hang the reader off an existing Flask app under /reader.

    Everything lives under one prefix so nothing can collide with the routes
    the Speak and Listen tabs already own, and so the page needs one line
    changed rather than thirty.
    """
    from flask import request, jsonify, send_from_directory, send_file

    os.makedirs(LIB_DIR, exist_ok=True)

    @flask_app.get("/reader")
    @flask_app.get("/read")
    def reader_page():
        f = os.path.join(STATIC_DIR, "reader.html")
        if not os.path.exists(f):
            return ("reader.html is not installed in static/", 404)
        return send_file(f)

    @flask_app.get("/reader/static/<path:fn>")
    def reader_static(fn):
        return send_from_directory(STATIC_DIR, fn)

    # ---- what can speak, and how ----

    @flask_app.get("/reader/api/voices")
    def r_voices():
        """The thirty, in the shape the page already understands.

        Deliberately the SAME object MA Reader Web's page was built around —
        id, vkey, name, lang, sex, engine, label — rather than a new one. The
        page's voice grid, its remembering, its "which one is current" test
        and its voice bar all read that shape, and adapting thirty rows of
        data is a smaller and far safer change than rewriting the machinery
        that displays them.

        `sex` is MEASURED, not guessed. Google publishes no gender, so the
        alternative to measuring it was writing down what the names sound
        like, which is somebody's belief with a table around it. voicesex.py
        takes the median pitch of each voice's own audio; `borderline` marks
        the two that sit near the line, where pitch alone does not settle it.
        """
        st = load_state()
        emo, pace = st.get("emotion", "Neutral"), st.get("pace", "normal")
        sx = VSX.table()
        out = []
        for n in app_module.VOICES:
            rec = sx.get(n) or {}
            out.append({"id": n, "vkey": vkey_for(n, emo, pace), "name": n,
                        "lang": "gem", "sex": rec.get("sex", ""),
                        "f0": rec.get("f0"), "by": rec.get("by", ""),
                        "borderline": bool(rec.get("borderline")),
                        "engine": "edge",
                        "label": app_module.VOICE_TIMBRE.get(n, "clear")})
        return jsonify(out)

    @flask_app.post("/reader/api/voicesex")
    def r_voicesex():
        """Move a voice to the other row, by hand, for good."""
        j = request.get_json(force=True, silent=True) or {}
        v, sex = j.get("voice"), j.get("sex")
        if v not in app_module.VOICE_TIMBRE:
            return jsonify({"ok": False, "error": "no voice called %r" % v}), 400
        VSX.set_by_hand(v, sex)
        return jsonify({"ok": True, "rows": VSX.rows(app_module)})

    @flask_app.post("/reader/api/voicesex/measure")
    def r_voicesex_measure():
        """Measure whatever has no answer yet. Costs one short synthesis per
        voice with no cached preview, and nothing for the rest."""
        j = request.get_json(force=True, silent=True) or {}
        _t, spent = VSX.ensure_all(app_module, budget=int(j.get("budget", 30)))
        return jsonify({"ok": True, "spent": spent,
                        "rows": VSX.rows(app_module)})

    # ---- endpoints the page asks for at boot, answered honestly ----
    # The page was built against an app with two engines, a language
    # catalogue and a Speechify account. It asks about all of them before it
    # will draw anything. Answering "none of that here" is three lines each
    # and leaves the boot path untouched; editing the boot path instead would
    # mean changing the one piece of the page that must not break.

    @flask_app.get("/reader/api/langs")
    def r_langs():
        return jsonify({"langs": [{"key": "gem", "name": "Gemini",
                                   "label": "Gemini voices"}]})

    @flask_app.get("/reader/api/cro_voices")
    def r_cro_voices():
        return jsonify({"cro": [], "eng": []})

    @flask_app.get("/reader/api/speechify/status")
    def r_sp_status():
        return jsonify({"ok": False, "voices": [], "keys": [], "failed": [],
                        "accent": "uk", "current": "", "reason": "no Speechify here"})

    @flask_app.get("/reader/api/browser")
    @flask_app.post("/reader/api/browser")
    def r_browser():
        return jsonify({"mode": "chrome"})

    @flask_app.get("/reader/api/keys")
    def r_keys():
        return jsonify({"keys": [], "note": "Gemini keys live in the Keys tab"})

    @flask_app.get("/reader/api/groq/status")
    def r_groq_status():
        return jsonify({"ok": False, "count": 0,
                        "reason": "nothing here but Google"})

    @flask_app.post("/reader/api/lang/detect")
    def r_lang_detect():
        return jsonify({"lang": load_state().get("lang", "eng")})

    @flask_app.get("/reader/api/emotions")
    def r_emotions():
        groups = []
        for group, lab, glyph, text, spoken in app_module.EMOTIONS:
            if not groups or groups[-1]["group"] != group:
                groups.append({"group": group, "items": []})
            groups[-1]["items"].append({"label": lab, "glyph": glyph,
                                        "direction": text, "spoken": spoken})
        return jsonify({"groups": groups,
                        "paces": [p[0] for p in app_module.PACES]})

    # ---- state ----

    @flask_app.get("/reader/api/state")
    def r_state_get():
        return jsonify(load_state())

    @flask_app.post("/reader/api/state")
    def r_state_post():
        return jsonify(save_state(request.get_json(force=True, silent=True) or {}))

    # ---- the library ----

    @flask_app.post("/reader/api/prepare")
    def r_prepare():
        j = request.get_json(force=True, silent=True) or {}
        raw = (j.get("text") or "").strip()
        if not raw:
            return jsonify({"error": "nothing to read"}), 400
        return jsonify(text_payload(lib_save(raw)))

    @flask_app.get("/reader/api/library")
    def r_library():
        return jsonify(lib_list())

    @flask_app.get("/reader/api/library/<tid>")
    def r_library_open(tid):
        if not os.path.isdir(os.path.join(LIB_DIR, tid)):
            return jsonify({"error": "no such text"}), 404
        return jsonify(text_payload(tid))

    @flask_app.post("/reader/api/library/<tid>/delete")
    def r_library_delete(tid):
        return jsonify({"ok": lib_delete(tid)})

    @flask_app.post("/reader/api/library/delete_bulk")
    def r_library_delete_bulk():
        j = request.get_json(force=True, silent=True) or {}
        n = sum(1 for t in (j.get("ids") or []) if lib_delete(t))
        return jsonify({"ok": True, "deleted": n})

    @flask_app.post("/reader/api/library/delete_all")
    def r_library_delete_all():
        n = sum(1 for r in lib_list() if lib_delete(r["id"]))
        return jsonify({"ok": True, "deleted": n})

    # ---- one sentence, one clip ----

    def _unit(tid, vkey, idx):
        st = load_state()
        parts = (vkey or "").split("__")
        voice = parts[0] if parts and parts[0] else st.get("voice", "Charon")
        emotion = parts[1] if len(parts) > 1 else st.get("emotion", "Neutral")
        pace = parts[2] if len(parts) > 2 else st.get("pace", "normal")
        if voice not in app_module.VOICE_TIMBRE:
            return None, None, "no voice called %r" % voice
        return ensure_unit(app_module, tid, vkey, idx, voice, emotion, pace)

    @flask_app.get("/reader/api/audio/<tid>/<vkey>/<int:idx>.wav")
    def r_audio(tid, vkey, idx):
        wav, _js, err = _unit(tid, vkey, idx)
        if err:
            return jsonify({"error": err}), 400
        return send_file(wav, mimetype="audio/wav", conditional=True)

    # No bounds endpoint: it served the word times, and the only timing
    # left is the clip's own length, which the audio element already knows.

    return flask_app
