# DELIVERY RECORD

**v1, 5.9.2026.** What was measured, and what was not tested.

## The gate

    build is fresh          1-google-tts-stt-v1.sh matches src/
    installer is whole      --verify passes
    TEST 1  mechanism       32 checks   0 failed
    TEST 2  running app     22 checks   0 failed
    TEST 3  ugly cases      33 checks   0 failed
    TEST 4  upgrade         19 checks   0 failed
                           106 checks   0 failed

Run on Linux with real keys, 5.9.2026.

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

## Two bugs found by the tests, not by use

Both would have passed any hand test against the real API. Written up in
`DEVELOPMENT.md`.

- the quota parser read every daily wall as a minute limit
- a prepaid account with no credit was retried forever

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
- **`gtt-update` end to end.** It cannot be run until this repository has two
  versions in it. Its parts were checked: the listing call, the version compare,
  and `--verify` on the download. The path that actually replaces a running
  updater is covered by the rename check in test 4.
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
