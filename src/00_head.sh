#!/usr/bin/env bash
# @@HEADER@@
#
# GOOGLE TTS AND STT, one roof over the two halves of the same job.
#
#   Speak    text in, audio out. Thirty voices, direction in plain English,
#            two speakers in one pass. The MA Reader side.
#   Listen   audio in, text out. The Maha Transcribe side.
#   Keys     every account tested, every limit measured, what is left today.
#
# Both halves run on ONE key ring and ONE fallback, which is the reason they
# are under one roof at all: two apps with separate key handling keep two
# ledgers, and two ledgers that each think they own the daily budget are both
# wrong by dinner time.
#
#   bash @@FILENAME@@                 install, then run the tests
#   bash @@FILENAME@@ --keys FILE     install, and take the keys out of FILE
#   bash @@FILENAME@@ --quiet         install, no tests
#   bash @@FILENAME@@ --verify        check this file is whole, change nothing
#
# --keys takes ANY file: a note, a .env, a JSON export, a CSV, a markdown
# table. It finds the keys, keeps the account names where they are there, and
# adds only the ones the ring does not already hold. Nothing is ever
# duplicated and nothing already in the ring is rewritten. The same picker is
# in the Keys tab, so a file can be dropped in later without the terminal.
#
# Leaves two words behind:
#
#   gtt          the menu, and the server on localhost:7311
#   gtt-update   fetch the newest installer from GitHub and run it
#
# No key is in this file. The ring lives at ~/.gemini_keys, chmod 600, and is
# shared with gemini_vo.py and gemini_quota.py. An install with no keys is a
# working install that cannot speak yet.

set -u

GTT_VERSION="@@VERSION@@"
GTT_FILE="@@FILENAME@@"
GTT_REPO="markoboskoauroville/GOOGLE_TTS_STT"

# --- the platform layer, and nothing below this block knows the platform ---
if [ -d "/data/data/com.termux/files/usr" ]; then
  PLATFORM="termux"
  BIN="${PREFIX:-/data/data/com.termux/files/usr}/bin"
else
  PLATFORM="macos"
  BIN="$HOME/bin"
fi
APPHOME="$HOME/.google_tts_stt"
APP="$APPHOME/app.py"
KEYS="$HOME/.gemini_keys"
OUT="$APPHOME/out"

VERIFY_ONLY=0
QUIET=0
IMPORT=""
NEXT_IS_KEYS=0
for a in "$@"; do
  if [ "$NEXT_IS_KEYS" = "1" ]; then IMPORT="$a"; NEXT_IS_KEYS=0; continue; fi
  case "$a" in
    --verify) VERIFY_ONLY=1 ;;
    --quiet|--no-test) QUIET=1 ;;
    --keys) NEXT_IS_KEYS=1 ;;
    --keys=*) IMPORT="${a#--keys=}" ;;
    -h|--help)
      printf 'usage: bash %s [--keys FILE] [--quiet] [--verify]\n' "$GTT_FILE"; exit 0 ;;
  esac
done

if [ -t 1 ]; then
  AM="\033[38;5;214m"; SAND="\033[38;5;223m"; OK="\033[1;32m"
  WARN="\033[1;33m"; BAD="\033[1;31m"; DIM="\033[0;90m"; OFF="\033[0m"
else
  AM=""; SAND=""; OK=""; WARN=""; BAD=""; DIM=""; OFF=""
fi

say()   { printf "  %b\n" "$1"; }
blank() { printf "\n"; }
step()  { printf "  ${AM}>${OFF} %-34s" "$1"; }
done_() { printf "${OK}ok${OFF}\n"; }
skip_() { printf "${DIM}%s${OFF}\n" "${1:-skipped}"; }
fail_() { printf "${BAD}%s${OFF}\n" "${1:-failed}"; }

banner() {
  blank
  printf "  ${AM}  ____  ____  ____ ${OFF}\n"
  printf "  ${AM} / ___||_  _||_  _|${OFF}   ${SAND}GOOGLE TTS AND STT${OFF}  ${AM}%s${OFF}\n" "$GTT_VERSION"
  printf "  ${AM}| |  _   ||    ||  ${OFF}   ${DIM}speak · listen · keys${OFF}\n"
  printf "  ${AM}| |_| |  ||    ||  ${OFF}   ${DIM}one ring, one ledger, one roof${OFF}\n"
  printf "  ${AM} \\____| |__|  |__| ${OFF}\n"
  blank
}

# ---------------------------------------------------------------- verify
if [ "$VERIFY_ONLY" = "1" ]; then
  banner
  n=$(grep -c '' "$0" 2>/dev/null || echo 0)
  step "file"; printf "%s lines\n" "$n"
  step "app payload"
  grep -q 'GTT_APP_EOF' "$0" && done_ || { fail_ "missing"; exit 1; }
  step "closing marker"
  [ "$(grep -c '^GTT_APP_EOF$' "$0")" -ge 1 ] && done_ || { fail_ "truncated"; exit 1; }
  step "shell syntax"
  bash -n "$0" >/dev/null 2>&1 && done_ || { fail_; exit 1; }
  blank; say "${OK}whole${OFF}"; blank; exit 0
fi

banner
say "${DIM}platform${OFF}  $PLATFORM"

mkdir -p "$APPHOME" "$OUT" "$BIN"

# ---------------------------------------------------------------- python
PY=""
for c in python3 python; do command -v "$c" >/dev/null 2>&1 && PY="$c" && break; done
step "python"
if [ -z "$PY" ]; then
  fail_ "not found"
  say "${DIM}Termux: pkg install python   macOS: brew install python${OFF}"
  exit 1
fi
printf "%s\n" "$($PY -V 2>&1 | awk '{print $2}')"

# ---------------------------------------------------------------- flask
step "flask"
if $PY -c "import flask" >/dev/null 2>&1; then
  skip_ "already there"
else
  printf "${DIM}installing${OFF}"
  $PY -m pip install flask --break-system-packages -q >/dev/null 2>&1 \
    || $PY -m pip install flask -q >/dev/null 2>&1
  printf "\r"; step "flask"
  $PY -c "import flask" >/dev/null 2>&1 && done_ || { fail_; exit 1; }
fi

# waitress if it is there, the dev server with a warning if it is not
step "waitress"
if $PY -c "import waitress" >/dev/null 2>&1; then
  skip_ "already there"
else
  $PY -m pip install waitress --break-system-packages -q >/dev/null 2>&1 \
    || $PY -m pip install waitress -q >/dev/null 2>&1
  $PY -c "import waitress" >/dev/null 2>&1 && done_ || skip_ "dev server instead"
fi

# ---------------------------------------------------------------- ffmpeg
step "ffmpeg"
if command -v ffmpeg >/dev/null 2>&1; then
  skip_ "already there"
else
  skip_ "Listen takes wav mp3 flac ogg aac only"
  say "${DIM}Termux: pkg install ffmpeg   macOS: brew install ffmpeg${OFF}"
fi

# ---------------------------------------------------------------- key ring
step "key ring"
if [ ! -f "$KEYS" ]; then
  cat > "$KEYS" <<'KEY_EOF'
# One account per pair of lines: the label, then the key, then a blank line.
# Delete these three comment lines once the first account is in.
KEY_EOF
  chmod 600 "$KEYS"
  skip_ "created empty"
else
  chmod 600 "$KEYS"
  KN=$(grep -cE '^(AIza[A-Za-z0-9_-]{20,}|AQ\.[A-Za-z0-9_-]{20,})$' "$KEYS" 2>/dev/null || echo 0)
  printf "%s accounts\n" "$KN"
fi

# ---------------------------------------------------------------- the app
step "app"
cat > "$APP.new" <<'GTT_APP_EOF'
