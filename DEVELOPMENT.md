# DEVELOPMENT

Every bug, fix, and reason. Appended, never rewritten.

---

## 5.9.2026 — v1, the first build

### Why the two apps came together

MA Reader and Maha Transcribe were each going to grow their own Gemini key
handling. They would then have had two rings, two fallbacks and two ledgers,
and two ledgers against one daily budget are both wrong the moment either one
spends. One roof, one ring, one count.

### The daily limits were not what anybody thought

The published tables disagree with each other and with the API. The way to
learn a limit is to trip it: a 429 states the number it just enforced.

    Quota exceeded for metric: …generate_content_free_tier_requests,
    limit: 5, model: gemini-3.6-flash

Measured this way: TTS is **3 a minute and 10 a day**, per account, per model.
An earlier estimate in the same session put the daily speech ceiling in the
hundreds of hours. It is between twelve and forty-eight. The estimate had been
built on the minute limit and an assumed daily limit, and the assumed number
was out by more than an order of magnitude.

### The quota parser read every daily wall as a minute limit

Found by test 3, not by use. The regex for the quota id expected a space after
the colon, which is how Google pretty-prints its JSON, so it worked perfectly
against the real API and failed on anything compact. The consequence would have
been a key retried all day against a wall it had already hit. Fixed by parsing
the JSON properly and keeping the regex only for a body that will not parse.

This is exactly the case the four tests exist to catch: it would have passed
every hand test, because every hand test used the real API.

### A prepaid account with no credit was retried forever

Also found by test 3. An empty prepaid account answers 429, the same status as
a rate limit, so the rate-limit branch ran first and the account went back on
the list. Waiting never helps in that case. The check now runs before the
rate-limit branch and the account is marked dead on the first refusal.

Two of the twenty-one accounts in the ring are in this state, which is how the
case was known to exist at all.

### is_daily was pulled out of read_quota

Not for tidiness. Test 1 could not reach the daily-versus-minute decision
without going through the parser, and a rule that cannot be tested alone is a
rule that gets tested by accident. It is four lines and it now has its own
checks.

### The commands are renamed, never truncated

`gtt-update` runs the installer that rewrites `gtt-update`. A plain `cat >`
truncates the file the running shell is still reading from, and bash then
continues at its old byte offset into whatever now occupies it. Small files
survive because bash had already buffered them. Luck is not a mechanism. Each
command is written beside its own name and renamed over the top; test 4 proves
the rename does not disturb a shell mid-read, with a script that sleeps two
seconds and is replaced while it sleeps.

### The installer is generated, not written twice

The app is a Python source and the installer is a shell file that carries it.
Written by hand that is two copies with a rule about keeping them in step,
which is the failure the manifest names by name. `tools/build_installer.py`
emits the installer from `src/`, stamps each source hash into the header, and
`--check` fails when the shipped file is stale. The gate runs `--check` first,
so a stale installer cannot pass.

### The page was rebuilt to the design language

The first draft hid the player until there was something to play, and hid the
result box until there was a result. Three layouts, two jumps, and the tallest
element arriving last. Everything is now drawn in the first frame and dimmed
with opacity and pointer-events, which do not touch layout, so an element
occupies the same space idle as it does active. Palette moved to the house one:
near-black, amber for the lit thing, sand for ink, red kept for faults only.

### A key leaked into a chat transcript on the way to this build

While reading the uploaded key file, the first command printed it. The filter
was written for `AIza` and the file was full of `AQ.` keys, so the redaction
matched nothing and printed everything. This is the exact trap `apis/gemini.md`
records, and it caused the same leak once before. All twenty-one keys need
rotating. Nothing in this repository holds a key, and the Keys tab never sends
a whole one to the page.

---

## 5.9.2026 — v2, the file picker

### Why

Copying a key file into place by hand is a step that gets skipped, done wrong,
or done twice. Done twice is the expensive one: the same keys land in the ring
again under slightly different names, the rotation then thinks it has thirty-six
budgets when it has eighteen, and every second request hits a wall the ledger
did not expect.

So the app takes the file and does the copying itself, and the merge is the
part that had to be right.

### Finding keys and naming them are two different jobs

Kept in separate functions on purpose. Finding is a regular expression and is
never wrong about what a key looks like. Naming is guesswork over the shape of
whatever file this was — JSON, CSV, a markdown table, a note. A wrong label
costs nothing, and separating them means a clever labelling idea can never lose
a key. Test 1b tests the two halves separately for the same reason.

### The picker and the ring reader disagreed about what a key is

Found by the new binding check in test 1. The picker accepted
`AQ.` plus twenty characters, and `load_ring` required a line longer than
thirty. A key between those two lengths imported successfully, reported
success, and then read back as an empty ring. There is now one `KEY_RE`,
defined above `load_ring`, used by both. Two definitions of the same thing are
two places to drift apart, and the drift here was silent in the worst way: the
app said it had done the thing it had not done.

### JSON exports were being labelled with fragments of JSON

The first version walked the JSON and used the dict key as the name, which
works for `{"tribal": "AQ..."}` and fails for `{"name": "tribal", "key":
"AQ..."}` — the field holding the key is called `key`, which strips to nothing,
so it fell back to the line above, which inside JSON is a fragment of JSON. The
first real file tried, a two-record export, produced accounts named
`{"name":"tribal","key`.

Now the walk looks for a sibling `name`, `label`, `account`, `title`, `id` or
`alias` field in the same object, and when the whole file parses as JSON the
JSON names REPLACE the line-based guesses instead of filling in beside them.

### Dependencies say when they are already there

`already there` in grey rather than `ok` in green. The green tick was being read
as "I installed this for you", which mattered on a machine where ffmpeg was
already present and the run looked identical to one where it had just been
fetched.

### get.sh, because the install command must not carry a version

The installer filename carries its number at both ends, which is right for a
file you keep and wrong for a command you type: `bash 1-google-tts-stt-v1.sh`
went stale the moment v2 existed, and it had already been handed over. `get.sh`
has no number, asks the repository which installer is newest, verifies the
download and runs it, passing its arguments through. MAHA_COMMUTE solved this
the same way and this is that shape.

### Two faults in the tests themselves

A test that overwrote the ring mid-file and left the five checks below it
looking at one key instead of two. And test 4 inheriting `GEMINI_KEYS` from the
environment, so the sandbox's import went into the real ring and the sandbox's
own ring stayed empty. Both were the test lying rather than the app breaking,
which is the failure mode the manifest warns about: any detail the system keys
on has to match reality or the test proves nothing about reality.

---

## 5.9.2026 — v3, AQ. is the format, and Termux installs its own dependencies

### The manifest had the two key formats the wrong way round

`apis/gemini.md` called `AIza` "the long-standing one" and `AQ.` "the newer
format". True when it was written, and it reads backwards now: `AQ.` is the
only format Google issues, and a chat skimming that table writes an `AIza`
filter and finds nothing. Which is exactly the leak the same file warns about,
and exactly what happened on the first command of the session that built this
app.

Corrected in the manifest, with the reason written next to it so the next chat
does not have to be told twice. The free-tier image note was corrected in the
same commit: no image model answers on the free tier any more, measured across
twenty-one accounts.

### AIza is still read, and that is deliberate

The instruction was not to use those keys. The app still *matches* the format,
because reading is not issuing: a ring assembled over two years holds AIza keys
that still authenticate, and a filter that drops them loses working accounts in
silence. Silent loss is worse than a loud failure. So they are read, and marked
`old AIza format` everywhere they appear — the import report, the Keys tab —
so the accounts to replace are visible rather than guessed at.

`AQ.` now comes first in the regular expression and first in every list, which
is the only part of this that is cosmetic and the part most likely to stop the
next person writing an `AIza` filter.

### Termux installs its own dependencies

v2 found python missing and told you to run `pkg install python` yourself.
Asking someone holding a phone to run one more command by hand is asking them
to stop. `pkg` is right there; the installer now uses it for python and for
ffmpeg, and says `already there` in grey when they are present. Termux has no
PEP 668 restriction and needs no venv, so that is the whole dependency story on
Android.

### Test 4 no longer spends a real key

It copied the real ring in to have something to preserve. But what it proves is
that what is on disk survives an install — it never calls the provider — so a
real key there was spent for nothing and the test could not run once the keys
were retired. It fabricates its own now, including a legacy AIza one, and
checks that too is still in the ring afterwards. Test 2 remains the only test
that needs a live account, which is now the only thing standing between this
repository and a full green gate.

---

## 5.9.2026 — v4, the updater stopped depending on the GitHub API

Found by running `get.sh` against the live repository rather than trusting it.
It answered `cannot reach GitHub`, twice, twenty seconds apart. GitHub was fine:

    403 API rate limit exceeded for 35.196.153.210

The API allows sixty requests an hour to an unauthenticated caller and counts
them **per address**. On a shared host that is everyone on the host. On a phone
on mobile data it is everyone on the carrier's NAT, which is a number you
cannot influence and cannot see coming. An updater that fails on someone else's
traffic is not an updater.

So `LATEST` is now written beside the installer by the build tool and read from
`raw.githubusercontent.com`, which is a CDN with no such limit. The API call
survives as a fallback for the case where `LATEST` is missing, and the name
that comes back either way is checked against the filename pattern before it is
used to build a URL. `--check` fails if `LATEST` does not name the installer
that was just built, so the two cannot drift.

The lesson is the one the manifest already has: anything outside the process
needs a deadline and a second path, and the way to find out whether it has one
is to run it, not to read it.

---

## 5.9.2026 — v5, two faults off a photograph of a phone

### "1 of 4 green" on a phone with no keys in it

The installer is supposed to notice an empty ring and skip the tests. It did
not, and the reason is one of the oldest traps in shell:

    KEYCOUNT=$(grep -cE '<pattern>' "$KEYS" 2>/dev/null || echo 0)

**`grep -c` prints `0` and exits 1** when it matches nothing. The `|| echo 0`
then appends a second zero, `KEYCOUNT` becomes the three characters `0\n0`,
`[ "$KEYCOUNT" -lt 1 ]` errors with *illegal number*, the `if` is therefore
false, and the else branch runs the whole gate against a ring with nothing in
it. Four provider tests fail, one ledger test passes, and the phone says *a
test failed* on a completely healthy install.

`|| true` is enough, because grep prints its count whether or not it found
anything, and the result is then stripped to digits before it is compared. The
same construction was in the head, where it only made the summary line read
`0 0 accounts`.

Test 4 now installs into an empty home and asserts three things: that it says
the ring is empty, that it does **not** run the provider tests, and that it does
not report a failure. Those three would have caught this before it left.

### The empty ring now says so once, not four times

Four failures that all mean *there are no keys* is four chances to read the
wrong reason. `gtt test` checks the ring first and stops with the one sentence
that matters and the command that fixes it.

### gtts

The app is called Google TTS and STT, so `gtts` is what the hand types, and it
was typed on the first day by the person who chose the name `gtt`. A command
that exists under one name and is reached for under another has a bug in its
name. Both now exist; `gtts` is two lines that exec `gtt`.

---

## 5.9.2026 — v6, the browser is the app

### `gtt` starts it, and the panel is a picture

Baba, off a photograph of the phone: *this server is a bit different than Maha
Commute. It just needs to start the app automatically inside the browser.*

MAHA COMMUTE's panel is a launcher for four separate servers and the keys are
one of its verbs. This has one server and one page, and every setting on it, so
a menu in front of the page is a door in front of a door. `gtt` now prints the
panel once as a splash and starts the app; the app opens the browser. `gtt menu`
still gives the interactive panel for when the terminal is where your hands are.

`webbrowser.open` does not work on Termux — it looks for desktop browsers and
desktop environment variables, finds neither, returns False and says nothing —
so the chain is `am start`, `termux-open-url`, `xdg-open`/`open`, `webbrowser`.
And `am start` prints its failure and still exits zero, so its output is read
rather than its exit code.

### An empty ring stopped blocking the start

v5 exited with *no keys found in ~/.gemini_keys* and never opened anything.
The picker that fixes an empty ring is on the page, so refusing to open the page
is refusing to let anybody fix it. The photograph showed exactly that: the error,
then the menu, and no way forward from either. The server now starts whatever
the ring holds and says what it found.

### AIza is gone, and I was told twice

`modules/keyring.md`: *no tool, script or detector in this project looks for the
old prefix. Not as a fallback, not as a second guess, not in a comment as an
example.* Baba, 3.9.2026, and the module records that he has had to say it in
every chat. v3 read that instruction and kept AIza anyway, on the reasoning that
dropping a format still in use loses working accounts silently.

The reasoning was not wrong; it was answering a question nobody asked. The rule
about never dropping a key for its shape is about IMPORTING, and it is honoured
by the maybes list: an old token is reported as an unknown shape and left for a
person to decide about. It is not honoured by hard-coding a retired prefix into
the detector. Both rules hold at once and v6 holds both.

### The key tester rewritten around five words

Ported from `modules/keyring.md` §2d and §2e rather than invented, because the
distinction is the expensive part. Calling *no credit* working sends the ring at
a wall. Calling it *refused* has somebody delete a live account they only needed
to top up. And the retry hint is checked before the money words, because Google
answers a spent account and an impatient one with the same status and the same
word — match on *quota* and you tell somebody to delete a live key because they
pressed Test twice in one second.

Delete removes the refused and only the refused. Busy is never deleted. Nothing
is destroyed: removed keys go to a file, chmod 600, and Put back returns them
through the same merge the picker uses, so restoring cannot double a key.

---

## 5.9.2026 — v7, the action row is letters

`R un`, `T est`, `K eys`, `O utput`, `U pdate`, `I mport`, `Q uit`. Every label
is spelled by its own key, which is the rule MAHA COMMUTE's function row already
follows: a key whose letter does not begin its word has to be read rather than
recognised, and a row that has to be read is a row that gets read every time.
Termux has no F keys on a soft keyboard, so the letter is what is actually
pressed and the numbers were only there because mc put some there.

The v6 numbers still work — fingers that learned them in the last hour should
not be punished — but they are no longer drawn. Two labels for one action is two
things to read.

Padded on the plain text with the colour wrapped around the letter only, because
printf counts the bytes of an escape sequence as width and a coloured cell handed
to a width comes out short by exactly the length of its escapes.

Test 4 now checks the drawn label and the case arm agree letter by letter, so a
label cannot be reworded later without its key moving with it.

### A test that was lying, again

`the old server is running during the upgrade` started failing, and the app was
fine. The test starts a server on a fixed port; a previous run had left one
behind, so the new one exited *address already in use* and the check read that
as the old server having died. It asks the operating system for a free port now.
Second time in this project a fixed detail in a test has produced a false
failure, and both times the app was innocent.

---

## 5.9.2026 — v8, the right Maha Transcribe

### I read the wrong repository, and the manifest now says which is which

Baba: *you were referencing my wrong Maha Transcribe Streamlit. When Marko said
reference Maha Transcribe, you never go to Maha Transcribe Streamlit. You always
go to Maha Transcribe for Termux and terminal.*

`keyring.md` §9 names `MAHA_TRANSCRIBE_STREAMLIT` as the reference
implementation, and that is correct — for **provider code**: the HTTP calls, the
status mapping, the ring. I took it as permission to treat that repository as
the whole of Maha Transcribe, which sent me to a Streamlit app for the shape of
a Termux one.

Both files now say so. `START_HERE.md` has a table of the names that have been
got wrong, because that is the file every chat reads first, and §9 carries the
boundary in its own paragraph.

### What actually came across from the terminal edition

`portpick.py`, `localguard.py` and `console.py`, condensed into this one file
with their comments intact, per the house rule about reading the file that
already solves a problem.

The port picker matters more than it looks: the thing sitting on 7311 is very
often this app still running from before, so a launcher that refuses to start on
a busy port is blocking on its own success case. And the port it actually bound
is what the browser opens and what the guard checks — tell the guard the wrong
number and it refuses every request from the page it just opened.

The guard matters because this app now deletes keys. Binding to loopback does
not stop a page you have open in another tab from making your browser POST here:
Host reflects where the browser actually connected, which is correctly 127.0.0.1
even for a cross-site fetch. Three checks, and the page itself still loads
without any of them, because typing an address in sends no Origin.

### The look is ma-reader-web's

The AGY tokens at the top of `maha_transcribe.html` are the same ones the reader
page uses, so the three apps read as tabs of one thing rather than three
products. Monospace throughout, one centred unit on a dark ground, pill tabs
with amber for the active one. The palette I had invented at v1 was close but
not the same, which is the worst kind of close.

### The Keys tab is Key_Tester's item_key.xml

A card per account, the status as a glyph and a word, and the actions on the row
they act on: test, models, delete. Baba asked for exactly this and the Android
app already had it. Testing one account by retesting twenty spends nineteen
requests to answer a question about one.

TEST ALL draws every row first as `… testing` and then fills the verdicts in,
because twenty rows arriving one at a time is a page that jumps.

---

## 5.9.2026 — v9, Maha Transcribe vendored whole

Baba: *port the whole app as it is, only changing the engine. Don't invent new
apps.*

So the page is not rebuilt, not redesigned and not summarised.
`src/30_transcribe.html` is `maha_transcribe.html` byte for byte, and the
installer carries it — the installer is 213 KB now, which is a third of
MAHA_COMMUTE's and the same idea.

The swap is three anchors in `tools/engine_patches.py`, applied at build time.
The upstream app already had exactly one dispatch point, `transcribeDispatch`,
and one readiness check, `serviceReady`. Those are the seams its author built,
and using them is the difference between changing an engine and rewriting an
app. Everything else — the recording, the queue, the archive, the correction,
the translation, the settings — is untouched, including the AssemblyAI code,
which is still in the file and simply no longer reached.

A missing anchor kills the build. A silent no-op would ship a page that looks
right and calls AssemblyAI with keys it does not have, and that failure would
not appear until the first recording.

### The first attempt broke on its own escaping

The patch table was generated inside a string inside a generator, and the
JavaScript escape sequences went through two layers of Python quoting and came
out as a syntax error. It lives in its own file now, as plain literals. A patch
table nobody can read is a patch table nobody will check.

### MA Reader Web is not done, and it is not a size problem

Its page is 258 KB and its server 167 KB, and both could be vendored the same
way. The reason it is not is the engine.

Edge TTS streams **word boundary events** alongside the audio, and the highlight
rides on those. `MA_READER_ENGINE` exists to carry that alignment between two
apps, which is how much it matters. **Gemini TTS returns audio and nothing
else** — no timings, no marks. Swapping the engine there means either losing the
highlight, which is the app, or producing the timing some other way: a forced
aligner, or sentence-level timing derived from audio length. Both are new work
with their own accuracy and their own ways of being wrong.

That is a decision rather than an implementation detail, so it is written down
here and in DELIVERY_RECORD rather than guessed at. Vendoring the reader without
an engine would put a reader in the repository that cannot read.
