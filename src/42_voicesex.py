"""Which voices are male and which are female, measured rather than guessed.

Google publishes ONE adjective per voice — "informative", "breathy", "firm" —
and nothing else. No gender, no age, no accent. The rule this project already
follows is that A BLANK IS A FACT AND A GUESS IS NOT, which is why `sex` was
empty everywhere else in this app and why no table of names was ever written
down: "Charon sounds male" is a thing somebody believed, not a thing anybody
checked.

Two rows of voices, male above and female below, needs the fact. So it is
measured, from the audio, which is not a guess: the median fundamental
frequency of a voice is the pitch it actually speaks at.

MEASURED HERE, 18.9.2026, all thirty. Fourteen were free — they already had a
cached preview — and sixteen cost one short synthesis each, once, forever.

    MALE, 17                          FEMALE, 13
     87 Enceladus  breathy            160 Zubenelgenubi casual      <-- on the line
     92 Charon     informative        176 Zephyr        bright
    103 Alnilam    firm               184 Vindemiatrix  gentle
    105 Algieba    smooth             186 Achernar      soft
    105 Algenib    gravelly           188 Aoede         breezy
    106 Umbriel    easy going         195 Laomedeia     upbeat
    112 Fenrir     excitable          205 Sulafat       warm
    119 Sadachbia  lively             213 Kore          firm
    126 Pulcherrima forward           213 Leda          youthful
    127 Puck       upbeat             229 Callirrhoe    easy going
    129 Schedar    even               239 Erinome       clear
    133 Sadaltager knowledgeable      246 Despina       smooth
    136 Orus       firm               262 Autonoe       bright
    136 Gacrux     mature
    137 Achird     friendly
    139 Rasalgethi informative
    155 Iapetus    clear              <-- on the line

AND HERE IS THE HONEST PART, because the first version of this comment was
written after measuring only the fourteen free ones and said something nicer.

On those fourteen the two clusters were separated by FORTY-NINE HERTZ with
nothing whatsoever inside the gap, and it was tempting to write that down as
the finding. With all thirty in, the gap is gone: Rasalgethi at 139, Iapetus
at 155, Zubenelgenubi at 160, Zephyr at 176. The distribution is continuous
straight through the middle, and the two voices either side of the line are
five hertz apart.

So the line is a CONVENTION, not a discovery. It is still in the right place —
it is where adult speech separates, and twenty-eight of the thirty sit clear
of it by a comfortable margin — but Iapetus and Zubenelgenubi are a coin toss
that pitch alone cannot settle, and anything within twelve hertz of the line
is flagged `borderline` so the interface can say so rather than present a
coin toss as a measurement.

The measurement is made once per voice and written down. It costs one short
synthesis for a voice with no cached preview, nothing at all for one that has
it, and never anything again.

AND IT CAN BE OVERRULED. A measurement is a fact about pitch, not a ruling
about a voice, and a low woman or a high man is an ordinary thing. Anything
set by hand is recorded as set by hand and is never re-measured.
"""

import array
import json
import math
import os
import subprocess

HOME = os.path.expanduser("~/.google_tts_stt")
SEX_FILE = os.path.join(HOME, "voice_sex.json")

SR = 16000
# The middle of the gap that was actually observed (137 -> 186), not a number
# taken from a table. If a future voice lands near it, that is worth knowing
# and worth showing, rather than worth rounding away.
SPLIT_HZ = 160.0
F0_MIN, F0_MAX = 60.0, 400.0


# ---------------------------------------------------------------- measuring

def _decode(path):
    """One channel of 16 kHz signed 16-bit, whatever the file was."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(SR),
             "-f", "s16le", "-"],
            capture_output=True, timeout=120).stdout
    except Exception:
        return None
    if not out:
        return None
    a = array.array("h")
    a.frombytes(out[:len(out) // 2 * 2])
    return a


def median_f0(pcm):
    """Median fundamental frequency over the voiced frames, or None.

    Autocorrelation, and deliberately only over the LOUDER frames: the quiet
    ones are breath, room tone and the tails of consonants, and they produce
    confident nonsense. A frame also has to correlate with itself well enough
    to be periodic at all, which is what separates a vowel from a hiss.
    """
    if not pcm:
        return None, 0
    win, hop = int(SR * 0.040), int(SR * 0.020)
    lo, hi = int(SR / F0_MAX), int(SR / F0_MIN)
    frames, energies = [], []
    for i in range(0, len(pcm) - win, hop):
        f = pcm[i:i + win]
        energies.append(math.sqrt(sum(float(v) * v for v in f) / win))
        frames.append(f)
    if not energies:
        return None, 0
    thr = sorted(energies)[int(len(energies) * 0.6)]      # the louder 40%
    vals = []
    for f, e in zip(frames, energies):
        if e < thr or e < 200:
            continue
        m = sum(f) / len(f)
        x = [float(v) - m for v in f]
        r0 = sum(v * v for v in x)
        if r0 <= 0:
            continue
        best, bestlag = 0.0, 0
        for lag in range(lo, hi):
            s = 0.0
            # stride two: at 16 kHz a pitch period is 40 to 270 samples, so
            # every other sample is still ample, and it halves the work on a
            # phone
            for k in range(0, len(x) - lag, 2):
                s += x[k] * x[k + lag]
            s /= (r0 * 0.5)
            if s > best:
                best, bestlag = s, lag
        if bestlag and best > 0.30:
            vals.append(SR / float(bestlag))
    if not vals:
        return None, 0
    vals.sort()
    return vals[len(vals) // 2], len(vals)


def classify(f0):
    if not f0:
        return ""
    return "M" if f0 < SPLIT_HZ else "F"


# ------------------------------------------------------------------- the table

def table():
    try:
        d = json.load(open(SEX_FILE, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write(d):
    try:
        tmp = SEX_FILE + ".part"
        json.dump(d, open(tmp, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, SEX_FILE)
    except Exception:
        pass


def set_by_hand(voice, sex):
    """Move a voice to the other row and keep it there.

    Recorded as `hand` so the measurer never argues with it afterwards. This
    is not a correction to the pitch — the pitch was right — it is a different
    question being answered by the only one who can.
    """
    sex = "M" if str(sex).upper().startswith("M") else "F"
    d = table()
    rec = d.get(voice) or {}
    rec["sex"] = sex
    rec["by"] = "hand"
    d[voice] = rec
    _write(d)
    return d


def _sample_for(app, voice):
    """A file to measure: a cached preview if there is one, else a new one.

    Goes through the app's own preview path rather than synthesising on the
    side, so the clip lands in the preview cache, is reused by the Voice
    screen, and is counted against the ledger like every other request.
    """
    for _group, lab, _glyph, _text, _spoken in app.EMOTIONS:
        h, _p = app.preview_key(voice, lab)
        hit = app.preview_path(h)
        if hit:
            return hit, True
    r = app.preview(voice, "Neutral")
    if not r.get("ok"):
        return None, False
    p = os.path.join(app.PREVIEWS, r["file"])
    return (p if os.path.exists(p) else None), bool(r.get("cached"))


def measure_one(app, voice, force=False):
    """Measure one voice and remember it. Returns its record."""
    d = table()
    rec = d.get(voice) or {}
    if not force and rec.get("by") == "hand":
        return rec
    if not force and rec.get("f0"):
        return rec
    path, was_cached = _sample_for(app, voice)
    if not path:
        return rec
    f0, n = median_f0(_decode(path))
    if not f0:
        return rec
    rec = {"f0": round(f0, 1), "frames": n, "sex": classify(f0),
           "by": "measured", "free": bool(was_cached),
           # near enough to the line that pitch alone is not an answer
           "borderline": abs(f0 - SPLIT_HZ) <= 12.0}
    d[voice] = rec
    _write(d)
    return rec


def ensure_all(app, voices=None, budget=None):
    """Measure whatever has no answer yet.

    `budget` caps how many NEW syntheses may be spent in one go, because this
    shares its daily allowance with the reading and the reading is the point.
    Voices with a cached preview are free and are never counted against it.
    """
    spent = 0
    for v in (voices or app.VOICES):
        d = table()
        rec = d.get(v) or {}
        if rec.get("sex"):
            continue
        _path, was_cached = None, False
        for _g, lab, _gl, _t, _s in app.EMOTIONS:
            h, _p = app.preview_key(v, lab)
            if app.preview_path(h):
                was_cached = True
                break
        if not was_cached:
            if budget is not None and spent >= budget:
                continue
            spent += 1
        measure_one(app, v)
    return table(), spent


def rows(app):
    """The two rows, each in the app's own voice order.

    A voice with no answer yet is in NEITHER row rather than dropped into one
    of them: an unmeasured voice put among the men is a guess wearing a
    measurement's clothes, which is the thing this file exists to avoid.
    """
    d = table()
    male, female, unknown = [], [], []
    for v in app.VOICES:
        s = (d.get(v) or {}).get("sex", "")
        (male if s == "M" else female if s == "F" else unknown).append(v)
    return {"male": male, "female": female, "unknown": unknown}
