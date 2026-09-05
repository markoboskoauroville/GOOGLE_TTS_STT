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
rm -f "$BIN/gtt.new" "$BIN/gtts.new" "$BIN/gtt-update.new"

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
case "\${1:-run}" in
  run|"") MENU=0 ;;
  menu)   MENU=1 ;;
  test)   exec "\$PY" "\$APP" test ;;
  keys)   exec \${EDITOR:-nano} "\$KEYS" ;;
  import) shift; exec "\$PY" "\$APP" import "\$@" ;;
  out)    exec ls -la "\$OUT" ;;
  update) exec gtt-update ;;
  *)      MENU=0 ;;
esac

panel() {
  printf "\n"
  printf "  \${AM}GOOGLE TTS AND STT\${OFF} $GTT_VERSION\n"
  printf "  +---------------------+---------------------+\n"
  printf "  |1 Speak              |2 Listen             |\n"
  printf "  |  text becomes audio |  audio becomes text |\n"
  printf "  |  thirty voices      |  any format ffmpeg  |\n"
  printf "  +---------------------+---------------------+\n"
  printf "  |3 Keys               |4 free               |\n"
  printf "  |  import and test    |                     |\n"
  printf "  |  what is left today |  room for a fourth  |\n"
  printf "  +---------------------+---------------------+\n"
  printf "  \${DIM}all four are tabs on the page, and the page is where\n"
  printf "  everything is done. This is the picture of it.\${OFF}\n"
}

if [ "\$MENU" = "1" ]; then
  while true; do
    panel
    printf "\n  1 run      2 test     3 keys     4 output\n"
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
fi

# The plain word starts the app and lets the app open the browser. Everything
# is done on the page, keys included, so there is nothing to choose here first.
panel
exec "\$PY" "\$APP"
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

step "gtts"
# The app is called Google TTS and STT, so gtts is what the hand types. It was
# typed on the first day. A command that exists under one name and is reached
# for under another is a command with a bug in its name.
cat > "$BIN/gtts.new" <<GTTS_ALIAS_EOF
#!/usr/bin/env bash
# gtts - the same thing as gtt. Both names work; gtt is the shorter one.
exec "$BIN/gtt" "\$@"
GTTS_ALIAS_EOF
chmod +x "$BIN/gtts.new"
mv -f "$BIN/gtts.new" "$BIN/gtts"
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
# grep -c PRINTS 0 and EXITS 1 when it matches nothing. So `|| echo 0` appends
# a second zero and KEYCOUNT becomes the two characters "0\n0", which is not a
# number, so [ -lt ] errors, the if is false, and the else branch runs the gate
# against an empty ring. That is what "1 of 4 green" on a fresh phone was.
# grep always prints a count when the file exists, so || true is enough, and
# the tr guards against anything else arriving with a newline in it.
KEYCOUNT="$(grep -cE '^AQ\.[A-Za-z0-9_-]{20,}$' "$KEYS" 2>/dev/null || true)"
KEYCOUNT="$(printf '%s' "$KEYCOUNT" | tr -dc '0-9')"
[ -z "$KEYCOUNT" ] && KEYCOUNT=0
if [ "$QUIET" = "1" ]; then
  say "${DIM}tests skipped by --quiet${OFF}"
  RC=0
elif [ "$KEYCOUNT" -lt 1 ]; then
  say "${WARN}the ring is empty, so there is nothing to test yet.${OFF}"
  blank
  say "Run ${SAND}gtt${OFF}. It opens the page, and the Keys tab has the file"
  say "picker — that is where the keys go. Or from here if you prefer:"
  say "  ${DIM}gtt import /sdcard/Download/your-keys.txt${OFF}"
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
  say "  ${SAND}gtt${OFF}          starts it and opens the browser"
  say "  ${DIM}gtts${OFF}         the same thing, for when that is what you type"
  say "  ${DIM}gtt menu${OFF}     the panel, if you want it"
  say "  ${SAND}gtt test${OFF}     the four tests"
  say "  ${SAND}gtt import F${OFF} add accounts from any file, without duplicating"
  say "  ${SAND}gtt-update${OFF}   fetch the next version"
else
  say "${BAD}a test failed.${OFF} The app is installed. Fix the ring and run ${SAND}gtt test${OFF}"
fi
blank
exit 0
