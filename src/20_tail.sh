GTT_APP_EOF
mv -f "$APP.new" "$APP"
chmod 644 "$APP"
done_

step "transcribe page"
# MAHA_TRANSCRIBE_TERMUX_TERMINAL's own page, whole, with one function swapped.
cat > "$APPHOME/transcribe.html.new" <<'GTT_TRANSCRIBE_EOF'
@@TRANSCRIBE_HTML@@
GTT_TRANSCRIBE_EOF
mv -f "$APPHOME/transcribe.html.new" "$APPHOME/transcribe.html"
chmod 644 "$APPHOME/transcribe.html"
done_

# ------------------------------------------------------------------ reader
# The reading interface and the three modules behind it. Written beside the
# app rather than inside it: reader.py imports wordtime and voicesex by name,
# and a page of a quarter of a megabyte has no business being a Python string.
step "reader"
mkdir -p "$APPHOME/static"

# wordtime.py is not written any more and is removed if an older version of
# this app left one behind: it measured where each word fell, and nothing asks
# any more. Its only dependency was a provider that is not Google.
rm -f "$APPHOME/wordtime.py"

cat > "$APPHOME/voicesex.py.new" <<'GTT_VOICESEX_EOF'
@@VOICESEX_PY@@
GTT_VOICESEX_EOF
mv -f "$APPHOME/voicesex.py.new" "$APPHOME/voicesex.py"
chmod 644 "$APPHOME/voicesex.py"

cat > "$APPHOME/reader.py.new" <<'GTT_READER_PY_EOF'
@@READER_PY@@
GTT_READER_PY_EOF
mv -f "$APPHOME/reader.py.new" "$APPHOME/reader.py"
chmod 644 "$APPHOME/reader.py"

cat > "$APPHOME/static/reader.html.new" <<'GTT_READER_HTML_EOF'
@@READER_HTML@@
GTT_READER_HTML_EOF
mv -f "$APPHOME/static/reader.html.new" "$APPHOME/static/reader.html"
chmod 644 "$APPHOME/static/reader.html"

cat > "$APPHOME/static/marked.umd.js.new" <<'GTT_MARKED_EOF'
@@MARKED_JS@@
GTT_MARKED_EOF
mv -f "$APPHOME/static/marked.umd.js.new" "$APPHOME/static/marked.umd.js"
chmod 644 "$APPHOME/static/marked.umd.js"

cat > "$APPHOME/static/icon.svg.new" <<'GTT_ICON_EOF'
@@ICON_SVG@@
GTT_ICON_EOF
mv -f "$APPHOME/static/icon.svg.new" "$APPHOME/static/icon.svg"
chmod 644 "$APPHOME/static/icon.svg"
done_

# ------------------------------------------------------- which voice is which
# NEVER OVERWRITTEN. Google publishes no gender for the thirty voices, so this
# table was MEASURED — the median pitch of each voice's own audio — and it is
# shipped so that a new install has the two voice rows without spending
# sixteen syntheses out of a ten-a-day budget to find out what they are.
#
# But it is also where a voice moved by hand is recorded, and that is somebody
# deciding something the measurement could not. So an existing file is left
# exactly alone: shipped as a starting point, never as a correction.
step "voice rows"
if [ -f "$APPHOME/voice_sex.json" ]; then
  printf "kept yours\n"
else
  cat > "$APPHOME/voice_sex.json.new" <<'GTT_VOICESEX_JSON_EOF'
@@VOICE_SEX_JSON@@
GTT_VOICESEX_JSON_EOF
  mv -f "$APPHOME/voice_sex.json.new" "$APPHOME/voice_sex.json"
  chmod 644 "$APPHOME/voice_sex.json"
  printf "30 measured\n"
fi

# ------------------------------------------------------------ preview cache
# A preview is the same request every time, so the first press does not have to
# cost anything either. These were made once and shipped; the rest fill in as
# they are pressed. Never overwrites: a preview already on disk is already paid
# for and is identical anyway.
step "preview cache"
mkdir -p "$APPHOME/previews"
SEEDED=0
while IFS=' ' read -r NAME DATA; do
  [ -z "$NAME" ] && continue
  [ -f "$APPHOME/previews/$NAME" ] && continue
  printf '%s' "$DATA" | base64 -d > "$APPHOME/previews/$NAME.new" 2>/dev/null \
    && mv -f "$APPHOME/previews/$NAME.new" "$APPHOME/previews/$NAME" \
    && SEEDED=$((SEEDED+1)) || rm -f "$APPHOME/previews/$NAME.new"
done <<'GTT_SEED_EOF'
@@SEED_CACHE@@
GTT_SEED_EOF
HAVE=$(ls "$APPHOME/previews" 2>/dev/null | wc -l | tr -d ' ')
printf "%s ready, %s new\n" "$HAVE" "$SEEDED"

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
#
# ONE HOME, TWO SPELLINGS, AND THIS COMMAND IS SHARED BETWEEN THEM.
#
# \$PREFIX/bin is the same directory whether you are in Termux or inside the
# proot, so this one file is run from both. But the two spell the same home
# differently — /data/data/com.termux/files/home out here, /root in there —
# and they are the SAME DIRECTORY, same inode, reachable by either name from
# inside and by only one name from outside.
#
# So the path must not be frozen at install time. It was, and installing from
# inside the proot wrote /root into this file; run from Termux proper it then
# said "can't open file '/root/.google_tts_stt/app.py'" while the file was
# sitting right there under its other name. The app was fine. The spelling
# was not.
#
# Resolved here instead, every run, cheaply: whichever spelling has the app.
GTT_HOME=""
for _h in "\$HOME" /data/data/com.termux/files/home /root; do
  [ -n "\$_h" ] && [ -f "\$_h/.google_tts_stt/app.py" ] && GTT_HOME="\$_h" && break
done
if [ -z "\$GTT_HOME" ]; then
  printf "\n  GTT is not installed under any home this shell can see.\n"
  printf "  Looked in: \$HOME, /data/data/com.termux/files/home, /root\n\n"
  exit 1
fi
APP="\$GTT_HOME/.google_tts_stt/app.py"
PY="\$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)"
KEYS="\$GTT_HOME/.gemini_keys"
OUT="\$GTT_HOME/.google_tts_stt/out"
export HOME="\$GTT_HOME"
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
  printf "  \${DIM}R un  T est  K eys  O utput  U pdate  I mport  Q uit\n"
  printf "  are the keys, and each one spells its own word.\${OFF}\n"
}

if [ "\$MENU" = "1" ]; then
  while true; do
    panel
    # EVERY LABEL IS SPELLED BY ITS OWN KEY. R un, T est, K eys, O utput,
    # U pdate, I mport, Q uit. A key whose letter does not begin its word has
    # to be read rather than recognised, and this row is meant to be
    # recognised. The numbers still work because fingers that learned them in
    # v6 should not be punished, but they are not drawn any more: two labels
    # for one action is two things to read.
    # Padded on the plain text, the colour wrapped around the letter only.
    # printf counts the bytes of an escape sequence as width, so a coloured
    # string handed to %-10s comes out short by the length of its escapes and
    # every column after it walks left. Four cells of ten, then three.
    printf "\n  \${AM}R\${OFF} un       \${AM}T\${OFF} est      \${AM}K\${OFF} eys      \${AM}O\${OFF} utput\n"
    printf "  \${AM}U\${OFF} pdate    \${AM}I\${OFF} mport    \${AM}Q\${OFF} uit\n\n  > "
    read -rsn1 k; printf "\n\n"
    case "\$k" in
      r|R|1) "\$PY" "\$APP" ;;
      t|T|2) "\$PY" "\$APP" test ;;
      k|K|3) \${EDITOR:-nano} "\$KEYS" ;;
      o|O|4) ls -la "\$OUT" ;;
      u|U|5) gtt-update ;;
      i|I|6) printf "  path to the key file: "; read -r f; [ -n "\$f" ] && "\$PY" "\$APP" import "\$f" ;;
      q|Q|0) exit 0 ;;
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

# --------------------------------------------------------------- finished
blank
# INSTALLING DOES NOT SPEND YOUR KEYS. The tests are real calls to a real
# provider against a real ring, which is what makes them worth having and
# exactly why they must not run behind your back: a TTS account has ten
# requests a day, and an install that quietly takes a few of them has decided
# something on your behalf. Baba, 5.9.2026.
#
# `bash <installer> --test` still runs them, because asking for them is
# different from having them happen.
KEYCOUNT="$(grep -cE '^AQ\.[A-Za-z0-9_-]{20,}$' "$KEYS" 2>/dev/null || true)"
KEYCOUNT="$(printf '%s' "$KEYCOUNT" | tr -dc '0-9')"
[ -z "$KEYCOUNT" ] && KEYCOUNT=0
RC=0
if [ "$RUNTESTS" = "1" ]; then
  if [ "$KEYCOUNT" -lt 1 ]; then
    say "${WARN}--test was asked for, but the ring is empty.${OFF}"
  else
    say "${DIM}four tests, real keys, no mocks, because you asked${OFF}"
    blank
    "$PY" "$APP" test
    RC=$?
    blank
  fi
fi

# If a copy is still serving, the person is looking at the OLD version and the
# port is still held. Say it plainly: an installer that finishes silently while
# the old app is still on screen is an installer that looks like it failed.
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "http://127.0.0.1:7311/" >/dev/null 2>&1; then
  say "${WARN}A copy is still running on 7311.${OFF} It is still the old version"
  say "until you stop it. Press ${SAND}q${OFF} in it, then run ${SAND}gtt${OFF}."
  blank
fi
say "${OK}installed${OFF} $GTT_VERSION"
if [ "$KEYCOUNT" -lt 1 ]; then
  blank
  say "${WARN}No keys yet.${OFF} Run ${SAND}gtt${OFF} — it opens the page, and the KEYS"
  say "tab has the file picker. That is where they go. Or from here:"
  say "  ${DIM}gtt import /sdcard/Download/your-keys.txt${OFF}"
fi
blank
say "  ${SAND}gtt${OFF}          starts it and opens the browser"
say "  ${DIM}gtts${OFF}         the same thing, for when that is what you type"
say "  ${DIM}gtt menu${OFF}     the panel, if you want it"
say "  ${DIM}gtt test${OFF}     the four tests, when YOU want them"
say "  ${SAND}gtt import F${OFF} add accounts from any file, without duplicating"
say "  ${SAND}gtt-update${OFF}   fetch the next version"
if [ "$RC" -ne 0 ]; then
  blank
  say "${BAD}a test failed.${OFF} The app is installed either way."
fi
blank
exit 0
