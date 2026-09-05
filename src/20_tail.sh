GTT_APP_EOF
mv -f "$APP.new" "$APP"
chmod 644 "$APP"
done_

# ---------------------------------------------------------------- commands
# RENAME, NEVER TRUNCATE. gtt-update runs this installer, so while these lines
# execute the old gtt-update is still open and bash is still reading it. A
# plain `cat >` over that file truncates what the running shell is reading and
# it carries on at the old byte offset into whatever is there now. Small files
# survive by luck. Luck is not a mechanism. So each command is written beside
# its own name and renamed over the top: the rename swaps the directory entry,
# the running shell keeps its open file and reads to the end undisturbed, and
# nothing half written is ever reachable under the real name.
rm -f "$BIN/gtt.new" "$BIN/gtt-update.new"

step "gtt"
cat > "$BIN/gtt.new" <<GTT_CMD_EOF
#!/usr/bin/env bash
# gtt - Google TTS and STT $GTT_VERSION
APP="$APP"
PY="$PY"
KEYS="$KEYS"
OUT="$OUT"
if [ -t 1 ]; then AM="\033[38;5;214m"; SAND="\033[38;5;223m"; DIM="\033[0;90m"; OFF="\033[0m"
else AM=""; SAND=""; DIM=""; OFF=""; fi
case "\${1:-menu}" in
  run|"") ;;
  test)   exec "\$PY" "\$APP" test ;;
  keys)   exec \${EDITOR:-nano} "\$KEYS" ;;
  import) shift; exec "\$PY" "\$APP" import "\$@" ;;
  out)    exec ls -la "\$OUT" ;;
  update) exec gtt-update ;;
esac
while true; do
  printf "\n"
  printf "  \${AM}GOOGLE TTS AND STT\${OFF} $GTT_VERSION\n"
  printf "  +---------------------+---------------------+\n"
  printf "  |1 Speak              |2 Listen             |\n"
  printf "  |  text becomes audio |  audio becomes text |\n"
  printf "  |  thirty voices      |  any format ffmpeg  |\n"
  printf "  +---------------------+---------------------+\n"
  printf "  |3 Keys               |4 free               |\n"
  printf "  |  test every account |                     |\n"
  printf "  |  what is left today |  room for a fourth  |\n"
  printf "  +---------------------+---------------------+\n"
  printf "  \${DIM}1 2 3 all open the same page on localhost:7311\${OFF}\n\n"
  printf "  1 run      2 test     3 keys     4 output\n"
  printf "  5 update   6 import   0 quit\n\n  > "
  read -rsn1 k; printf "\n\n"
  case "\$k" in
    1|r|R) "\$PY" "\$APP" ;;
    2|t|T) "\$PY" "\$APP" test ;;
    3|k|K) \${EDITOR:-nano} "\$KEYS" ;;
    4|o|O) ls -la "\$OUT" ;;
    5|u|U) gtt-update ;;
    6|i|I) printf "  path to the key file: "; read -r f; [ -n "\$f" ] && "\$PY" "\$APP" import "\$f" ;;
    0|q|Q) exit 0 ;;
  esac
done
GTT_CMD_EOF
chmod +x "$BIN/gtt.new"
mv -f "$BIN/gtt.new" "$BIN/gtt"
done_

step "gtt-update"
cat > "$BIN/gtt-update.new" <<GTT_UPD_EOF
#!/usr/bin/env bash
# gtt-update - fetch the newest installer and run it.
# This file is rewritten by the installer it runs. That is safe only because
# the installer renames over it instead of truncating it. Do not "simplify"
# that into a cat.
set -u
REPO="$GTT_REPO"
TMP="\$(mktemp -d)"
trap 'rm -rf "\$TMP"' EXIT
if [ -t 1 ]; then AM="\033[38;5;214m"; BAD="\033[1;31m"; DIM="\033[0;90m"; OFF="\033[0m"
else AM=""; BAD=""; DIM=""; OFF=""; fi
printf "\n  \${AM}gtt-update\${OFF}  installed $GTT_VERSION\n\n"
# raw first, the API only if raw has nothing. The API is sixty an hour per
# address to an unauthenticated caller, and on mobile data that address is the
# carrier's, not yours.
NAME="\$(curl -fsSL "https://raw.githubusercontent.com/\$REPO/main/LATEST" 2>/dev/null | tr -d '\r\n ')"
if [ -z "\$NAME" ]; then
  LIST="\$(curl -fsSL "https://api.github.com/repos/\$REPO/contents/" 2>/dev/null)" || true
  NAME="\$(printf '%s' "\$LIST" | grep -o '"name": *"[0-9]*-google-tts-stt-v[0-9]*\.sh"' \
    | sed 's/.*"\(.*\)"/\1/' | sort -t v -k2 -n | tail -1)"
fi
case "\$NAME" in
  [0-9]*-google-tts-stt-v[0-9]*.sh) : ;;
  *) printf "  \${BAD}cannot work out which installer is newest\${OFF}, nothing changed\n\n"; exit 1 ;;
esac
NEWV="v\${NAME##*-v}"; NEWV="\${NEWV%.sh}"
if [ "\$NEWV" = "$GTT_VERSION" ]; then
  printf "  already on \$NEWV, nothing to do\n\n"; exit 0
fi
printf "  \${AM}\$NEWV\${OFF} is out, fetching\n"
curl -fsSL "https://raw.githubusercontent.com/\$REPO/main/\$NAME" -o "\$TMP/\$NAME" || {
  printf "  \${BAD}download failed\${OFF}, nothing changed\n\n"; exit 1; }
bash "\$TMP/\$NAME" --verify >/dev/null 2>&1 || {
  printf "  \${BAD}the download is not whole\${OFF}, nothing changed\n\n"; exit 1; }
printf "  \${DIM}running \$NAME\${OFF}\n"
exec bash "\$TMP/\$NAME"
GTT_UPD_EOF
chmod +x "$BIN/gtt-update.new"
mv -f "$BIN/gtt-update.new" "$BIN/gtt-update"
done_

# ---------------------------------------------------------------- PATH
case ":$PATH:" in
  *":$BIN:"*) : ;;
  *)
    blank
    say "${WARN}$BIN is not on your PATH.${OFF} Add this to your shell rc:"
    say "${DIM}    export PATH=\"\$HOME/bin:\$PATH\"${OFF}"
    ;;
esac

# ---------------------------------------------------------------- keys in
# Done AFTER the app is written, because the app owns the parser. One parser,
# one merge, one place where a duplicate could be created and therefore one
# place where it is prevented.
if [ -n "$IMPORT" ]; then
  blank
  if [ -f "$IMPORT" ]; then
    say "${DIM}reading keys from $IMPORT${OFF}"
    "$PY" "$APP" import "$IMPORT"
  else
    say "${BAD}no file at $IMPORT${OFF}, nothing imported"
  fi
fi

# ---------------------------------------------------------------- the gate
blank
KEYCOUNT=$(grep -cE '^(AQ\.[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,})$' "$KEYS" 2>/dev/null || echo 0)
if [ "$QUIET" = "1" ]; then
  say "${DIM}tests skipped by --quiet${OFF}"
  RC=0
elif [ "$KEYCOUNT" -lt 1 ]; then
  say "${WARN}no keys yet.${OFF} Put them in $KEYS, then run:  ${SAND}gtt test${OFF}"
  RC=0
else
  say "${DIM}four tests, real keys, no mocks${OFF}"
  blank
  "$PY" "$APP" test
  RC=$?
  blank
fi

if [ "$RC" -eq 0 ]; then
  say "${OK}installed${OFF} $GTT_VERSION"
  say "  ${SAND}gtt${OFF}          the menu, and the app on localhost:7311"
  say "  ${SAND}gtt test${OFF}     the four tests"
  say "  ${SAND}gtt import F${OFF} add accounts from any file, without duplicating"
  say "  ${SAND}gtt-update${OFF}   fetch the next version"
else
  say "${BAD}a test failed.${OFF} The app is installed. Fix the ring and run ${SAND}gtt test${OFF}"
fi
blank
exit 0
