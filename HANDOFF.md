# HANDOFF

**GOOGLE TTS AND STT v3. The finished state, nothing historical.**

## What it is

A server on `localhost:7311` with three tabs, installed by one file and started
by one word. `gtt` starts it and **opens the browser itself**. Everything is
done on the page: the keys, the testing, the deleting, all of it. The panel the
terminal draws is a picture of what the app does, not a place anything is set.

Speak makes audio from text. Listen makes text from audio. Keys imports, tests
and prunes the ring.

`gtt menu` still gives the old panel with keys on it, for when the terminal is
where your hands already are. Its action row is letters, each one spelling its
own word:

    R un   T est   K eys   O utput   U pdate   I mport   Q uit

The v6 numbers still work and are no longer drawn.

## Maha Transcribe, whole

`/transcribe` serves `MAHA_TRANSCRIBE_TERMUX_TERMINAL/maha_transcribe.html`
**byte for byte**, vendored at `src/30_transcribe.html`. Recording, the queue,
the archive, copy, correction, translation, the settings, the language picker,
all of it is the app already in use. Nothing was reimplemented and nothing was
redesigned.

**Only the engine changed**, and the swap is three anchors in
`tools/engine_patches.py`, applied at build time so the vendored file stays
identical to upstream and every change is visible in one readable place:

| anchor | upstream | here |
|---|---|---|
| `transcribeDispatch` | `aaiTranscribe`, AssemblyAI, keys in the browser's localStorage | POSTs the blob to `/api/listen`, so the server ring answers and the rotation, ledger and daily budget cover it |
| `serviceReady` | "does localStorage hold an assembly key" | asks `/api/health` whether the server ring holds any |
| the startup message | "no assemblyai keys" | comes from that health check |

A missing anchor is **fatal at build time**. Shipping the page untouched would
leave it calling AssemblyAI with keys it does not have, and it would look like a
working app right up to the first recording.

The AssemblyAI code is all still in the file, unreached. That is deliberate:
deleting it would be editing somebody else's app rather than changing its
engine, and the dispatch point is the seam its author already built.

## What was ported, and from where

Nothing here was written fresh where a file already solved it.

| from | what came across |
|---|---|
| `MAHA_TRANSCRIBE_TERMUX_TERMINAL/portpick.py` | the port is never a reason not to start, and the port actually bound is the one everything downstream uses |
| `MAHA_TRANSCRIBE_TERMUX_TERMINAL/localguard.py` | Host, Origin and a header only this page can send |
| `MAHA_TRANSCRIBE_TERMUX_TERMINAL/console.py` | plain lines and single keys, never a redrawn box; `quiet_flask`; degrade honestly with no terminal |
| `maha_transcribe.html` / ma-reader-web | the AGY tokens, the centred unit, the pill tabs, monospace throughout |
| `Key_Tester/item_key.xml` | a card per account with its actions on the row they act on |
| `Key_Tester` HANDOFF | the status glyphs and the five words |
| `MAHA_TRANSCRIBE_STREAMLIT/ttt/keyring.py` | the ring rules: never drop a key for its shape, a key file is a working note |

## The guard

This app deletes keys and spends quota, so binding to loopback is not enough: a
page you have open in another tab can make your browser send requests to
127.0.0.1, and Host reflects where the browser actually connected, which is
correctly 127.0.0.1 even for a cross-site fetch.

    1  HOST        must be a loopback name. Catches DNS rebinding.
    2  ORIGIN      if present, must be this app.
    3  X-Gtt-Local a header this page always sends and a cross-site request
                   cannot set at all.

The page itself loads on 1 and 2 alone, because typing the address in yourself
sends no Origin and no custom header. Everything under `/api/` needs all three.

## The port

Preferred, then the next fifteen, then whatever the system hands out. There is
no path through it that ends in "could not start" — and the thing on 7311 is
very often this app, still running from before. The number it actually bound is
what the browser opens and what the guard checks; telling the guard the wrong
one would refuse every request from the page it just opened.

## Opening the browser

`webbrowser.open` DOES NOT WORK on Termux: it looks for desktop browsers and
desktop environment variables, finds none, returns False and says nothing. The
chain that does work, in order: `am start`, `termux-open-url`, `xdg-open` or
`open`, and `webbrowser` last as a courtesy.

`am start` prints its failure and still exits zero — asking for a package that
is not installed writes *unable to resolve Intent* and returns success — so its
OUTPUT is read, never its exit code.

## An empty ring never blocks the start

v5 refused to start without keys, which put the picker that fixes an empty ring
behind the empty ring. The server starts either way and says how many accounts
it found.

## Key formats

**`AQ.` and nothing else.** `modules/keyring.md` is explicit: no tool, script or
detector in this project looks for the retired `AIza` prefix, not as a fallback,
not as a second guess, not in a comment as an example, because a detector that
knows both keeps the dead form alive in everybody's memory. v3 to v5 of this app
read `AIza` and were wrong to.

That does not break the other rule, NEVER DROP A KEY FOR ITS SHAPE. Shape only
decides what is imported. Anything else long and opaque, an old `AIza` token
included, comes back as an unknown shape and is reported, so nothing is lost in
silence.

One `KEY_RE`, defined above `load_ring`, used by the reader and the picker both.

## The five answers a key can give

Ported from `modules/keyring.md` §2d and §2e, order included.

| verdict | what it means | what happens |
|---|---|---|
| working | it did the work | use it |
| busy | throttled this minute | wait. **Never deleted.** |
| no credit | real key, live account, no money | top up, or delete on purpose |
| refused | revoked, mistyped, not a Gemini key | this is what Delete removes |
| unknown | the answer says nothing about the key | try again |

**The retry hint is checked first and wins.** Google answers a spent account and
an impatient one with the same status and the same word, so matching on *quota*
alone tells somebody to delete a live key because they pressed Test twice in one
second. `retryDelay`, `Retry-After`, `RetryInfo`, `QuotaFailure`, *per minute*,
*try again in* — any of those and it is a throttle whatever else the body says.
Only then the money words, and only the unambiguous ones: credit, balance,
depleted, insufficient, billing, payment, prepayment.

## The Keys tab

A card per account, from `Key_Tester/item_key.xml`: the label, the status as a
glyph and a word, the masked key, why, and three actions **on the row they act
on** — test, models, delete. The question is usually about one account, and
retesting twenty to answer it spends nineteen requests for nothing.

    \u25cf working     \u25d0 busy     \uff04 no credit     \u2717 refused     ? unknown

TEST ALL draws every row first with `\u2026 testing` and fills the verdicts in.
Nothing appears and nothing disappears; twenty rows arriving one at a time is a
page that jumps.

`models` lists what that account can reach. It answers 200 with zero credit, so
it says nothing about money — it is the catalogue, and it is worth seeing when a
model name stops working.

## Deleting, and undoing it

DELETE REFUSED removes the refused ones and only those. A busy account is never
deleted and neither is an unknown one. Every row also has its own delete.

Nothing is destroyed. Deleted entries move to `~/.google_tts_stt/removed_keys`,
chmod 600, and **Put back** returns them through the same merge the picker uses,
so a key cannot be doubled by being restored. A permanent condemnation that
cannot be undone is a bug wearing a rule's clothing.

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
