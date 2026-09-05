#!/usr/bin/env bash
# The one command that does not change between versions.
#
#   curl -fsSL https://raw.githubusercontent.com/markoboskoauroville/GOOGLE_TTS_STT/main/get.sh -o get.sh && bash get.sh
#
# The installer's own filename carries its version number at both ends, which
# is right for a file you keep and wrong for a command you type: the command
# would go stale the day v3 lands. So this file has no number in it, asks the
# repository which installer is newest, checks the download is whole, and runs
# it. Everything it passes on the way through goes to the installer:
#
#   bash get.sh --keys ~/Downloads/my-keys.txt
#   bash get.sh --quiet
set -u
REPO="markoboskoauroville/GOOGLE_TTS_STT"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -t 1 ]; then AM="\033[38;5;214m"; BAD="\033[1;31m"; DIM="\033[0;90m"; OFF="\033[0m"
else AM=""; BAD=""; DIM=""; OFF=""; fi

printf "\n  ${AM}GOOGLE TTS AND STT${OFF}  fetching the newest installer\n\n"
LIST="$(curl -fsSL "https://api.github.com/repos/$REPO/contents/" 2>/dev/null)" || {
  printf "  ${BAD}cannot reach GitHub${OFF}\n\n"; exit 1; }
NAME="$(printf '%s' "$LIST" | grep -o '"name": *"[0-9]*-google-tts-stt-v[0-9]*\.sh"' \
  | sed 's/.*"\(.*\)"/\1/' | sort -t v -k2 -n | tail -1)"
[ -z "$NAME" ] && { printf "  ${BAD}no installer in the repository${OFF}\n\n"; exit 1; }
printf "  ${DIM}%s${OFF}\n" "$NAME"
curl -fsSL "https://raw.githubusercontent.com/$REPO/main/$NAME" -o "$TMP/$NAME" || {
  printf "  ${BAD}download failed${OFF}\n\n"; exit 1; }
bash "$TMP/$NAME" --verify >/dev/null 2>&1 || {
  printf "  ${BAD}the download is not whole${OFF}, nothing was installed\n\n"; exit 1; }
exec bash "$TMP/$NAME" "$@"
