# HANDOFF

**GOOGLE TTS AND STT v3. The finished state, nothing historical.**

## What it is

A Flask server on `localhost:7311` with three tabs, installed by one file and
started by one word. Speak makes audio from text. Listen makes text from audio.
Keys tests every account and shows what is left of today.

## Key formats

`AQ.` is what Google issues. `AIza` is legacy, no longer handed out, still read,
and flagged as old format on the Keys tab and in every import report. Reading is
not issuing: dropping a format that still authenticates loses working accounts
without saying so.

One `KEY_RE`, defined above `load_ring`, used by the reader and the picker both.

## The file picker

One parser, one merge, one place a duplicate could be created and therefore one
place it is prevented. It is reached three ways and all three run the same code:

    bash get.sh --keys FILE     during the install
    gtt import FILE             from the terminal
    Keys tab → Add accounts     from the browser

**Finding keys and naming them are kept apart on purpose.** Finding is a regular
expression over the raw text and is never wrong about what a key looks like.
Naming is guesswork, allowed to be wrong, because a bad label costs nothing —
the key still works and the name can be edited. Keeping them separate means no
clever labelling idea can ever lose a key.

Names are taken, in this order: from the JSON if the whole file parses, from
the same line in front of the key, from the same line after it, then from the
nearest line above that is neither blank nor a comment. Nothing found means
`account 1`, `account 2`.

Merging never duplicates. A key already in the ring is skipped whatever name
the new file gives it, and the name already in the ring is the one kept. A new
key wanting a name that is taken is numbered. The ring is appended to, so
comments and hand edits in it survive. Written to a `.new` file and renamed
over the top, chmod 600.

A receipt is written to `~/.google_tts_stt/imports/` saying what was added and
what was skipped. It holds no key: the keys live in exactly one file and that
is not it.

## Where everything is

    ~/.gemini_keys              the ring, chmod 600, shared with gemini_vo.py
    ~/.google_tts_stt/app.py    the app, written by the installer
    ~/.google_tts_stt/ledger.json
    ~/.google_tts_stt/out/      every WAV Speak has made
    ~/.google_tts_stt/imports/  what each import added, with no keys in it
    $PREFIX/bin                 Termux, already on the PATH
    ~/bin                       macOS, may need adding to the PATH
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
    gtts             the same thing, because that is what gets typed
    gtt run          the server
    gtt test         the four tests
    gtt keys         edit the ring
    gtt import FILE  add accounts from any file, without duplicating
    gtt out          list what Speak has made
    gtt-update       fetch the next version and run it
