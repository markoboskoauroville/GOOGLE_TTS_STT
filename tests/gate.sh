#!/usr/bin/env bash
# The gate. Nothing leaves without this, and it runs the four in order.
#
#   bash tests/gate.sh              all four
#   bash tests/gate.sh --offline    1, 3 and the build check only, no keys spent
#
# Tests 2 and 4 spend real requests from the ring: about four TTS calls and a
# handful of flash-lite ones. On a day where the budget is tight, --offline
# still proves the mechanism and the ugly cases.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3 || command -v python)"
OFFLINE=0
for a in "$@"; do [ "$a" = "--offline" ] && OFFLINE=1; done

if [ -t 1 ]; then AM="\033[38;5;214m"; OK="\033[1;32m"; BAD="\033[1;31m"; DIM="\033[0;90m"; OFF="\033[0m"
else AM=""; OK=""; BAD=""; DIM=""; OFF=""; fi

FAILED=""
run() {
  printf "\n${AM}%s${OFF}\n" "$1"
  shift
  if "$@"; then :; else FAILED="$FAILED $1"; fi
}

printf "\n  ${AM}GOOGLE TTS AND STT${OFF}  the gate\n"

printf "\n${AM}build is fresh${OFF}\n"
"$PY" "$ROOT/tools/build_installer.py" --check || FAILED="$FAILED build"

printf "\n${AM}installer is whole${OFF}\n"
INST="$(ls "$ROOT"/[0-9]*-google-tts-stt-v[0-9]*.sh | head -1)"
bash "$INST" --verify >/dev/null && printf "   ok   %s verifies\n" "$(basename "$INST")" \
  || FAILED="$FAILED verify"

"$PY" "$ROOT/tests/test1_mechanism.py" || FAILED="$FAILED test1"
"$PY" "$ROOT/tests/test1b_parser.py" || FAILED="$FAILED test1b"

if [ "$OFFLINE" = "0" ]; then
  "$PY" "$ROOT/tests/test2_real.py" || FAILED="$FAILED test2"
else
  printf "\n${DIM}TEST 2 skipped by --offline${OFF}\n"
fi

"$PY" "$ROOT/tests/test3_ugly.py" || FAILED="$FAILED test3"

if [ "$OFFLINE" = "0" ]; then
  bash "$ROOT/tests/test4_upgrade.sh" || FAILED="$FAILED test4"
else
  printf "\n${DIM}TEST 4 skipped by --offline${OFF}\n"
fi

printf "\n"
if [ -z "$FAILED" ]; then
  printf "  ${OK}GATE GREEN${OFF}\n\n"
  exit 0
fi
printf "  ${BAD}GATE RED${OFF}%s\n\n" "$FAILED"
exit 1
