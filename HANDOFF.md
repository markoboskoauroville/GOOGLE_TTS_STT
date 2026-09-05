# HANDOFF

**GOOGLE TTS AND STT v1. The finished state, nothing historical.**

## What it is

A Flask server on `localhost:7311` with three tabs, installed by one file and
started by one word. Speak makes audio from text. Listen makes text from audio.
Keys tests every account and shows what is left of today.

## Where everything is

    ~/.gemini_keys              the ring, chmod 600, shared with gemini_vo.py
    ~/.google_tts_stt/app.py    the app, written by the installer
    ~/.google_tts_stt/ledger.json
    ~/.google_tts_stt/out/      every WAV Speak has made
    $PREFIX/bin/gtt             Termux
    ~/bin/gtt                   macOS

## The free tier, measured

Every number below was read out of a 429. When a quota is exceeded the API
states the limit it just enforced, so none of this comes from a table.

| model | for | per minute | per day |
|---|---|---|---|
| `gemini-2.5-flash-preview-tts` | Speak | 3 | **10** |
| `gemini-3.1-flash-tts-preview` | Speak | 3 | **10** |
| `gemini-3.1-flash-lite` | Listen | 15 | over 50, never reached |
| `gemini-3.6-flash` | Listen | 5 | **20** |
| `gemini-3.5-flash` | Listen | 5 | 20, assumed the same as its sibling |

Audio comes back at exactly 25 tokens a second and one call stops near 11,800
tokens, so **eight minutes of speech is the ceiling for a single request**.
Generation runs at about 1.8× realtime. Audio going the other way is also 25
tokens a second, and the 1M window means one Listen call holds about eleven
hours.

**The daily limits are the whole story.** Ten per account per model. With
eighteen live accounts that is 360 speech calls a day, which is twelve hours of
audio at ordinary take lengths and forty-eight if every call is run to its
ceiling. Listening is not a constraint at any scale this app will meet.

## The fallback

Every request walks the ring, most budget first.

| what came back | what happens |
|---|---|
| 429 naming a **minute** limit | next key, nothing spent, the limit is remembered |
| 429 naming a **daily** limit | that key is written off for this model until the reset, and the number is recorded |
| 429 saying prepayment depleted | the account is marked dead; waiting will never help |
| 401 | the key is marked dead |
| 503 | the model is busy, next key, nothing is blamed on the key |

Speak: `gemini-2.5-flash-preview-tts` → `gemini-3.1-flash-tts-preview`.
Listen: `gemini-3.1-flash-lite` → `gemini-3.6-flash` → `gemini-3.5-flash`.
Each model is then tried across every key, so a request only fails when every
account has refused it.

## The reset

Requests per day reset at **midnight Pacific**, which is 09:00 in Zagreb, and
stays 09:00 all year because both clocks move for daylight saving together.
Nothing carries over. The ledger notices the new Pacific day the first time it
is read and clears itself; what it *learned* about the limits survives, because
that is knowledge rather than spend.

Two things that mislead:

- **Quotas are per project, not per key.** Two keys made inside one Google Cloud
  project share one budget. Eighteen accounts is eighteen budgets only if they
  are eighteen projects.
- **The AI Studio dashboard shows peak usage over ninety days**, not today. It
  reads as stuck at 21/20 for a week and it is not.

## The ledger, and what it cannot know

It counts what this app spent. It cannot see what `gemini_vo.py`, a notebook or
the AI Studio web page spent on the same keys, so the budget on the Keys tab is
a ceiling, not a promise. The fallback repairs it as it goes: the first time a
key answers with a daily wall, the real number is written down and that key is
skipped until the reset.

## Build

`src/` is the truth and the installer is generated from it, with the hash of
each source stamped into the header. `tools/build_installer.py --check` fails
when the shipped file no longer matches, and the gate runs that check first.
The version lives in `src/10_app.py` as `VERSION` and nowhere else; the
filename carries it at both ends.

## Commands

    gtt              menu
    gtt run          the server
    gtt test         the four tests
    gtt keys         edit the ring
    gtt out          list what Speak has made
    gtt-update       fetch the next version and run it
