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
