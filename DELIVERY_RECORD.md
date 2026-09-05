# DELIVERY RECORD

**v17, 5.9.2026.** What was measured, and what was not tested.

## The gate

    build is fresh          17-google-tts-stt-v17.sh matches src/
    installer is whole      --verify passes
    TEST 1   mechanism      136 checks   0 failed
    TEST 1b  the parser      73 checks   0 failed
    TEST 3   ugly cases      59 checks   0 failed
    TEST 4   upgrade         58 checks   0 failed
                            326 checks   0 failed

TEST 2 was run against a fabricated ring at v8: everything structural passed —
the guard refuses an api call with no header, refuses another page's Origin,
refuses a foreign Host, and lets the page itself load; the page carries the
house tokens and the account cards. The provider half could not run, because
there is no working key.

**TEST 2 was NOT run for v3.** It is the one test that spends real provider
requests, and the keys used through v1 and v2 have been retired. It last ran
green at v2 with 32 checks. Test 4 was rewritten for v3 to fabricate its own
keys — it proves that what is on disk survives an install, which never needed a
working account — so the only thing now standing between a build and a green
gate is a live ring. Run `bash tests/gate.sh` with new keys in place and test 2
is the part that will tell you whether the provider side still works.

## The thirty-eight directions, measured 5.9.2026

Every one produced audio. Same sentence, same voice, only the direction
changing, compiled by the app itself. Eight takes transcribed back: not one
contains the parenthetical, so the direction is acted on rather than read out.

Against the Neutral take: Impatient 42% faster and 75% louder, Advertising 35%
faster and 90% louder, Sad 33% slower and 31% quieter, Sleepy 20% slower,
Whispered 25% quieter with the highest zero-crossing rate in the set. Sharp and
Bright come out loud and fast, Low and Still quiet and slow.

**Grateful is an outlier and it is reproducible.** 485 RMS against Neutral's
3212, and two retakes at 934 and 1203. Its direction text begins *quietly
grateful* and the model takes "quietly" as a level instruction. Unusable in a
mix without a gain ride. One word in `Emotions.kt` would fix it; that list is
Baba's, so it is reported rather than edited.

Eight sit close to Neutral on duration and level: Disappointed, Regretful,
Weary, Calm, Reverent, Anxious, Kind, Afraid. That is not a failure — Afraid has
the second highest ZCR in the set, so it is doing something these two measures
cannot see. Pitch and phrasing are where those live and nothing here can hear.

## Measured, not assumed

| | |
|---|---|
| TTS rate limit | 3 a minute, **10 a day**, per account per model. Read from the 429. |
| `gemini-3.6-flash` | 5 a minute, **20 a day** |
| `gemini-3.1-flash-lite` | 15 a minute, daily never reached |
| audio out | exactly 25 tokens a second |
| longest single call | 472 s of speech, about 11,800 tokens |
| generation speed | 91 s of audio in 51 s of wall clock, 1.8× realtime |
| audio in | also 25 tokens a second; 1M context is about 11 hours |
| the loop | Speak's WAV fed back to Listen returns the words that went in |

## The parser, measured

Seventeen file shapes, each holding the same two keys, each parsed correctly:
the plain ring, a bare list, everything on one line, dotenv, a JSON object,
JSON records with the name in a sibling field, CSV both ways round, a markdown
table, YAML, a handwritten note, quoted and comma'd, Windows line endings, no
trailing newline, inside a code fence, HTML, and keys buried in prose next to a
URL.

Eight shapes that contain no key and must yield none: empty, whitespace, prose,
a git sha, padded base64, a URL, a short lookalike, and the bare word `AIza`.
Plus a PNG, which must not raise, and a PNG with a key hidden in it, which must
still give the key. A megabyte of noise around one key finds the key.

Never duplicating, measured: the same file twice, an overlapping file, the same
key under a different name, the same key three times in one file, and a new key
wanting a name that is taken.

## Four bugs found by the tests, not by use

Both would have passed any hand test against the real API. Written up in
`DEVELOPMENT.md`.

- the quota parser read every daily wall as a minute limit
- a prepaid account with no credit was retried forever
- the picker and the ring reader disagreed about what a key is, so a key in
  between their two definitions imported successfully into a ring that then
  read back empty
- JSON exports with the name in a sibling field were labelled with fragments of
  JSON

## Measured at v6, without a live account

    verdict_for            eleven cases, including a 429 carrying BOTH a retry
                           hint and a money word, which must be busy
    delete and put back    a comment in the ring survives the rewrite, the file
                           stays 600, remove-restore twice does not duplicate
    the browser chain      written from modules/termux-app.md, unproven on a phone
    an empty ring          the server starts, the page serves, the picker works

## NOT DONE YET, AND IT IS HALF THE ASK

**MA Reader Web is not ported.** The page is 258 KB and its server is 167 KB,
and the reason it is not simply vendored the way Maha Transcribe was is not
size. It is that the reader's engine is **not** a drop-in swap:

- Edge TTS streams **word boundary events** with the audio. That is what the
  highlight rides on, and `MA_READER_ENGINE` exists specifically to carry that
  alignment between two apps.
- **Gemini TTS returns audio and nothing else.** No word timings, no marks.

So changing the reader's engine to Gemini means either losing the highlight,
which is the app, or generating the timing another way — a forced aligner, or
sentence-level timing from the audio length, both of which are new work with
their own accuracy and their own failure modes.

That is a decision, not an implementation detail, and it is Baba's to make. The
page is not vendored yet because vendoring it without an engine would put a
reader in the repository that cannot read.

## NOT TESTED

Named rather than left to silence.

- **Termux.** Everything platform-specific is in the installer prologue and the
  launcher, and both were exercised on Linux with the macOS branch. `pkg
  install`, `pip` inside Termux, `$PREFIX/bin`, `termux-open-url` and the wake
  lock are unproven on the device.
- **macOS proper.** Same code path as the Linux run, different machine.
- **A real upgrade from a real previous release.** There is no version before
  v1. Test 4 installs v1 over itself and hand-writes a ledger in an older shape
  so there is genuinely something from before to misread. From v2 the test uses
  the actual previous release and the stand-in comes out.
- **`u` in the console, end to end.** The exec path is checked by reading the
  installed app; it has not been pressed on a phone.
- **`gtt-update` end to end.** It needs a version newer than the installed one
  to actually replace anything. `get.sh` HAS now been run end to end against
  the live repository, which is how the API rate limit was found. Their parts were checked: the listing call, the version compare, and
  `--verify` on the download. The path that replaces a running updater is
  covered by the rename check in test 4. Run `gtt-update` once v3 exists and it
  will be proven or it will not.
- **A key file in a character encoding other than UTF-8.** Bytes are decoded
  with `errors="replace"`, which cannot corrupt a key — every character a
  Gemini key can contain is ASCII — but it has not been tried with a real
  UTF-16 or Latin-1 file.
- **A file over 8 MB.** Refused by size rather than parsed, which is a guess
  about what a key file is rather than a measurement.
- **waitress.** Installed and imported, but the app still starts the Flask
  development server. Wiring waitress in is v2.
- **The daily limit for `gemini-3.1-flash-lite`.** Never reached, so the budget
  assumes 50 a day and marks that row as a guess on the Keys tab.
- **`gemini-3.5-flash`'s daily limit.** Assumed to match `gemini-3.6-flash` at
  20 because they share every other limit. Not confirmed.
- **A ledger crossing midnight Pacific mid-request.** The rollover is tested by
  writing yesterday's date into the ledger, which is not the same as being
  inside a request when the clock turns over.

## Known and accepted

The ledger counts only what this app spends. Another tool on the same ring is
invisible to it, so the budget shown is a ceiling. The fallback corrects it the
first time a key answers with a wall.
