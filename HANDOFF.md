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

## The activity line

One line, under the tabs, **in every tab, always**. It says what the app is
doing and it says it even when the answer is nothing, because a line that only
appears when something is happening is a line you have to notice appearing.

Every call goes through one `api()` that carries a label, so there is no path
that does work silently. An app that reports the slow things and says nothing
about the quick ones teaches the hand that a still screen means broken, and then
a fast answer looks like a fault.

**Maha Transcribe reports up.** It runs in an iframe, and it posts its stages to
the page around it, so the line says what the app is doing whichever tab is on
screen. The stages are the ones that take real time:

    transcoding 412 KB with ffmpeg
    sending 143 KB to Google
    waiting for Google, 7s          <- counts up, because a silent minute reads as a hang
    receiving the transcript
    done, 24s transcribed

**An empty transcript is now a failure.** It used to read as success: a blank box
and a status saying done, which on screen is the same thing as nothing having
happened at all.

## The screen

Three pills and a cogwheel, and nothing else above the work. No title bar, no
tagline, no version: on a phone that was four lines of chrome before anything
you came for. The version lives in the settings panel.

**The cog is per tab.** It opens the settings for whatever is underneath it, so
it always means the same thing. On SPEAK that is the two voice slots, the actor
names and the voice browser. On KEYS it is what is installed and what the cache
holds. On LISTEN it points at Maha Transcribe's own panel.

**Choosing is in settings, the main screen is information.** The two slots on
SPEAK show who is speaking and in which voice, with a ▶ to hear it. They are not
controls; the controls are behind the cog.

**One spinner, and it runs on everything.** A braille cell, one character, 80 ms
a frame. It is the only thing on the screen that moves, so movement always means
the same thing. It runs on the quick things too: an app that spins for the slow
ones and freezes for the quick ones teaches you that a still screen means broken,
and then a fast answer looks like a fault.

## The page is an HTML file

`src/15_page.html`, inlined into the app by the build tool. It used to be a
triple-quoted python string, and that is what broke v13: a patch meant to reach
the JavaScript as `\'` went through two levels of escaping and arrived as a bare
quote, every `onclick` lost its argument, and the script died at parse. On the
phone that looked like *counting the cache* forever and a SPEAK button that did
nothing, because every function defined after the bad line never existed.

An HTML file cannot do that to itself, and there are no `onclick` attributes left
either: one delegated listener reads `data-` attributes, so there is no quoting
to get wrong. **Test 1 runs `node --check` over the script**, so a syntax error
now stops the build instead of the app.

## SPEAK, which is Sample Player with Hume swapped for Gemini

Ported from `SAMPLE_PLAYER`: two slots, a browser with a search box and facet
chips, and a bank of directions you insert rather than type. *A free text box is
a blank page, and a blank page in the middle of choosing a voice is the moment
somebody gives up and takes the default.*

**The thirty-eight directions are `Emotions.kt`, unchanged** — eight groups,
each with a one-character glyph so a direction can be found by shape before it
is read, and nothing is an emoji because a monospace grid of them is a mess of
different widths. Search across label, group and the direction itself.

**The voice facets are only what Google publishes.** `Roles.kt`'s lesson kept: a
blank is a fact, a guess is not. Hume gives four tags and Sample Player still
had to read the *names* to find the role. Google gives one adjective and nothing
else, so there is no gender facet, no age, no accent — a search box, the timbre,
and what you have starred.

### Previews are cached, and the first press is already paid for

A preview is the same request every time: the same voice, the same direction,
the same fixed sentence. So the second person to press play on *angry* is asking
a question that has already been answered, and answering it again costs one of
the ten requests that account has for the day.

**47 previews ship inside the installer** — 36 of the 38 directions on the
default voice and 11 other voices on Neutral — so an install with no keys at all
can still play them. Anything not shipped is fetched once, the first time it is
pressed, and never again. The button says which it was, `cached` or `new`,
because a preview that quietly spends a request looks free and the person finds
out at the daily wall.

**The key is the sha of the exact prompt that was sent**, not of the label. A
label is a name for a direction; if that direction's WORDS are ever edited the
audio must not still come back from the old key. Hashing what was actually sent
makes the invalidation automatic and impossible to forget. It never expires:
same input, same output, nothing for time to change.

`~/.google_tts_stt/previews`, and an upgrade never overwrites what is in it,
because everything in there has already been paid for.

### The tag

Invented, because Gemini has nothing like Hume's per-utterance `description`.
Hume takes an acting direction beside every line; Gemini takes **one** prose
direction for the whole call and a speaker name in front of each line. So the
tags are compiled, not passed through.

    <Viveka>                  this line is Viveka's
    <Viveka: Weary>           and he is weary
    <Viveka: Weary: slow>     and slow with it
    <Manan>                   now Manan

Angle brackets because they cannot be typed by accident in dialogue the way a
bracket or a slash can. Put the cursor where you want one and pick a direction;
the pace dropdown folds into the same tag.

`compile_script` turns that into a preamble naming both speakers and their
timbres, then one line each with its direction in parentheses. **Problems are
never silent**: a tag naming somebody with no voice, a direction that does not
exist, or a third speaker when Gemini takes two, all come back with the audio
and are shown. A line read in the wrong voice sounds like a bad model rather
than a typo.

## Maha Transcribe, inside the TRANSCRIBE tab

The TRANSCRIBE tab **is** the app. Not a link to it: a link is a second step and a
second page, and you cannot open a file in the tab you just left. It loads the
first time that tab is opened and is then left alone, because reloading it would
throw away a recording in progress.

`src/30_transcribe.html` is `MAHA_TRANSCRIBE_TERMUX_TERMINAL/maha_transcribe.html`
vendored, and `tools/engine_patches.py` holds nine edits applied at build time,
so the vendored file stays identical to upstream and every change is in one
readable place. A missing anchor is **fatal at build time**.

**One engine, and nothing to choose.**

| what | upstream | here |
|---|---|---|
| transcription | AssemblyAI, keys in localStorage | `/api/listen`, the server ring |
| correction and reshape | Claude or Gemini, then a model, then a spend budget | `/api/rewrite`, and the server picks |
| the model | four pickers in settings | none. The chain is tried in order and the first that answers wins |
| translate | a third tab | gone |
| keys | a ring per provider in this browser | the one shared ring, in the KEYS tab |

**The model is not a setting.** `modules/model-names.md`: a dated model string
is a time bomb — it fails with not_found before the request runs, so it never
shows in usage and looks exactly like a dead key. A picker in a settings panel
is a list that goes stale in somebody's localStorage.

What is left is recording, transcribing, correcting and the archive. The
AssemblyAI and Claude code is still in the file and unreached; deleting it would
be editing the app rather than changing its engine, and the two renderers that
wrote into the removed settings elements are guarded rather than cut, because
each is called from several places and a `null.innerHTML` throws during setup
and takes the whole page with it.

## The settings are shared

There is one ring, on the server, at `~/.gemini_keys`. The transcribe page has
no keys of its own and no key panels: its settings say where they live, and the
KEYS tab is where they are imported, tested and deleted. Both halves of the app
spend from the same ledger and the same daily budget.

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

## Audio, end to end

**Record at the best the phone will give.** The microphone is asked for mono
48 kHz with **echo cancellation, noise suppression and automatic gain off**.
That processing is tuned for a human on the other end of a call and it removes
exactly the quiet detail a transcriber needs. The recorder runs at 128 kbps. It
costs nothing that matters: the file lives on the phone for seconds before
ffmpeg reduces it, and reducing from a clean source is not the same as reducing
from one already thinned once.

**Chrome, Brave and Firefox.** Chrome and Brave record webm/opus. **Firefox does
not** — it produces ogg/opus and answers false for every webm type, so a
webm-only list leaves it with no recorder at all. The list is tried in order:
webm/opus, ogg/opus, webm, ogg, mp4.

**Everything passes through ffmpeg.** Picked files always did; a recording used
to go up as whatever the browser produced, which is a second pipeline for the
same job and the one nobody was testing. Both go through `/api/optimize-audio`
now.

**The target moved, because the engine changed.**

| | upstream, for AssemblyAI | here, for Gemini |
|---|---|---|
| rate | 16 kHz | **24 kHz** |
| bitrate | 32 kbps | **48 kbps** |
| tuning | voip | **audio** |

AssemblyAI resamples to 16 kHz internally, so bytes above that were pure waste.
Gemini is billed the same way — **measured: audio input is exactly 25 tokens a
second, whatever the bitrate** — so a bigger file costs nothing but the seconds
it takes to cross loopback. What 16/32 voip *was* costing is intelligibility:
voip tuning keeps a call understandable to a human ear and thins the
high-frequency detail that separates an s from an f. That is free to keep here,
so it is kept. 24 kHz holds everything up to 12 kHz; 48 kbps is transparent for
speech; "audio" rather than "voip" because the listener is a model trained on
clean speech, not somebody on a bad line.

## The vendored page needs its server

Maha Transcribe was written against **its own** server. It calls endpoints by
name and sends its own header, `X-Maha-Local`, on every one of them. Vendoring
the page without those is vendoring half an app, and the half that is missing
does not report as missing: the page asks `/api/ffmpeg`, gets a 403 or a 404,
and says **"ffmpeg not found on the server"** — on a phone with ffmpeg
installed.

So this server answers what that page asks for:

| endpoint | what it is |
|---|---|
| `/api/ffmpeg` | is the server side of the pipeline there |
| `/api/optimize-audio` | any file ffmpeg can decode, back as 16 kHz mono Opus |
| `/api/listen` | the engine swap |
| `/api/rewrite` | correction and reshape |
| `/api/health` | is the ring loaded |

`audioprep.py` came across whole, target and reasoning included: 16 kHz because
ASR resamples to it anyway, mono for the same argument about channels, Opus at
32 kbps tuned for voip because that is what carries a phone call. A two-hour
video becomes a same-length mono file usually under 20 MB. Measured here: a
1.17 MB WAV came back 96 KB, and that 96 KB transcribed correctly.

**The guard accepts both headers.** Test 1 now reads the BUILT page, collects
every `/api/` call in it and fails if this server does not answer one — the
check has to be on the built page, because the engine patches add calls the
vendored file does not contain.

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

## Updating

`u` in the console, or `gtt-update` from the shell. Either way the running copy
**ends first**: `u` hands the terminal back and `exec`s the updater, so this
process is replaced rather than becoming its parent. The port is freed, the
installer has the terminal to itself, and when it finishes you are at a shell
prompt with nothing old left running.

Run `gtt` again afterwards. The update does not restart it for you, because
starting a server is not something an installer should decide.

If an install runs while a copy is still serving on 7311 it says so, because a
finished installer sitting underneath a still-running old version looks exactly
like an installer that hung.

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
    gtt test         the four tests, when you ask for them
    gtt keys         edit the ring
    gtt import FILE  add accounts from any file, without duplicating
    gtt out          list what Speak has made
    gtt-update       fetch the next version and run it
