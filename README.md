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

**Termux**

    pkg install -y curl && curl -fsSL https://raw.githubusercontent.com/markoboskoauroville/GOOGLE_TTS_STT/main/get.sh -o get.sh && bash get.sh

Python and ffmpeg are installed by the installer itself with `pkg` if they are
not already there, and skipped with a word if they are. The command lands in
`$PREFIX/bin`, which is already on the PATH, so no rc file is touched.

**macOS**

    curl -fsSL https://raw.githubusercontent.com/markoboskoauroville/GOOGLE_TTS_STT/main/get.sh -o get.sh && bash get.sh

`get.sh` has no version number in it, so the command never goes stale. It reads
`LATEST` to find the newest installer, checks the download is whole, and runs
it. `LATEST` is fetched from raw.githubusercontent, not the GitHub API: the API
allows an unauthenticated caller sixty requests an hour **per address**, and on
mobile data that address belongs to the carrier. To hand it your keys at the same time:

    bash get.sh --keys ~/Downloads/whatever-the-file-is-called.txt

Termux and macOS. It finds the platform itself, installs Flask and waitress if
they are missing, notices whether ffmpeg is there, creates the key ring if you
have not made one, and then runs the four tests against real keys.

Two words are left behind:

    gtt          the menu, and the app on localhost:7311
    gtts         the same thing; both names work
    gtt-update   fetch the newest installer from this repository and run it

## The keys, and never copying a file by hand

Give the app the file however it was saved. A note with the account names
above the keys, a `.env`, a JSON export, a CSV, a markdown table, a page of
prose with the keys somewhere in it. It finds them, takes the account names
where they are there, invents them where they are not, and adds **only the
keys the ring does not already hold**.

    bash get.sh --keys ~/Downloads/keys.json      while installing
    gtt import ~/Downloads/more-keys.txt          any time after
    Keys tab → Add accounts from a file           without the terminal

The ring lives at `~/.gemini_keys`, chmod 600, shared with `gemini_vo.py` and
`gemini_quota.py`. An import appends to it: comments already in the file
survive, existing entries are never rewritten, and **a key already in the ring
is never added twice**, whatever name the new file gives it. A new key that
wants a name already taken is numbered rather than overwriting anything.

**`AQ.` is the format Google issues now.** Every key made in AI Studio today
looks like that. `AIza` keys are legacy and no longer handed out, and they are
still *read*: a ring assembled over two years holds AIza keys that still
authenticate, and a filter that drops them loses working accounts in silence,
which is worse than failing loudly. They are marked as old format wherever they
appear so you can see which accounts to replace. One regular expression, shared
by the ring reader and the picker. A long token in a format neither recognises
is reported rather than imported, because Google has changed this once and will
do it again.

No key is in this repository and none is ever sent to the page: six characters
at the front, four at the back.

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
    bash tests/gate.sh                          the tests
    bash tests/gate.sh --offline                1, 3 and the build check, no keys spent
