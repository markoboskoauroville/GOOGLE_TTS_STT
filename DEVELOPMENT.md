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
