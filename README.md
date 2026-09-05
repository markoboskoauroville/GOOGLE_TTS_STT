# GOOGLE TTS AND STT

**One roof over the two halves of the same job, on one key ring.**

    Speak    text in, audio out. Thirty voices, direction in plain English,
             two speakers in one pass. The MA Reader side.
    Listen   audio in, text out. The Maha Transcribe side.
    Keys     every account tested, every limit measured, what is left today.

Both halves run on the same Gemini free-tier ring and the same fallback. That
is the reason they are together: two apps with separate key handling keep two
ledgers, and two ledgers that each believe they own the daily budget are both
wrong by the evening.

## Install

    bash 1-google-tts-stt-v1.sh

Termux and macOS. It finds the platform itself, installs Flask and waitress if
they are missing, notices whether ffmpeg is there, creates the key ring if you
have not made one, and then runs the four tests against real keys.

Two words are left behind:

    gtt          the menu, and the app on localhost:7311
    gtt-update   fetch the newest installer from this repository and run it

## The key ring

`~/.gemini_keys`, chmod 600. Label line, key line, blank line.

    mantreshvar
    AQ.…

    kukljica
    AQ.…

Both Gemini key formats are read, `AIza…` and the newer `AQ.…`. No key is in
this repository and none is ever sent to the page: the Keys tab shows six
characters at the front and four at the back.

## Which document to open

| | |
|---|---|
| [`HANDOFF.md`](HANDOFF.md) | what it is now, and how it works |
| [`DEVELOPMENT.md`](DEVELOPMENT.md) | every bug and the reason behind every decision |
| [`DELIVERY_RECORD.md`](DELIVERY_RECORD.md) | what was measured, and what was not tested |
| [`docs/VISUAL_LANGUAGE.md`](docs/VISUAL_LANGUAGE.md) | how the screen looks and why |

## Build and gate

The installer is generated. `src/` is the truth.

    python3 tools/build_installer.py            write the installer
    python3 tools/build_installer.py --check    fail if the shipped file is stale
    bash tests/gate.sh                          the four tests
    bash tests/gate.sh --offline                1, 3 and the build check, no keys spent
