#!/usr/bin/env bash
# TEST 4 — THE UPGRADE, FROM THE VERSION BEFORE
#
# Closes off "it works on a machine that has never run the old version".
# Nobody installs this fresh. They have the previous one, with their keys,
# their ledger, their WAVs, and quite possibly the server still running.
#
#   1  install the previous version, for real
#   2  USE it: spend from the ledger, make a file, keep the keys
#   3  leave it RUNNING
#   4  install the new one on top
#   5  check every one of those survived
#
# HONEST NOTE, and it belongs in DELIVERY_RECORD.md too: there is no published
# version before v1. So step 1 installs v1 itself as the stand-in, and the
# ledger is written in an older shape by hand so there is genuinely something
# from "before" to misread. From v2 this test uses the real previous release
# and the stand-in comes out.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALLER="$(ls "$ROOT"/[0-9]*-google-tts-stt-v[0-9]*.sh 2>/dev/null | head -1)"
SANDBOX="$(mktemp -d)"
PY="$(command -v python3 || command -v python)"
PASS=0; FAIL=0

ok()   { printf "   ok   %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "   FAIL %s\n" "$1"; FAIL=$((FAIL+1)); }
want() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }

printf "TEST 4 — the upgrade, over what is already there\n"
[ -z "$INSTALLER" ] && { printf "   no installer built, run tools/build_installer.py\n"; exit 1; }

export HOME="$SANDBOX"
unset GEMINI_KEYS        # the sandbox has its own ring; the real one is not it
mkdir -p "$HOME"
APPHOME="$HOME/.google_tts_stt"
BIN="$HOME/bin"

# --- 1. the previous version, for real -------------------------------------
# Fabricated keys, on purpose. This test proves that what is on disk survives
# an install; it never calls the provider, so a real key here would be spent
# for nothing.
printf 'old label\nAQ.Ab8RN6TESTKEYTESTKEYTESTKEYTEST\n' > "$HOME/.gemini_keys"
chmod 600 "$HOME/.gemini_keys"
KEYSUM_BEFORE="$(cksum < "$HOME/.gemini_keys")"

bash "$INSTALLER" --quiet >/dev/null 2>&1
[ -f "$APPHOME/app.py" ] && ok "the previous version installed" || bad "the previous version installed"
[ -x "$BIN/gtt" ] && ok "gtt was there before the upgrade" || bad "gtt was there before the upgrade"

# --- 2. use it -------------------------------------------------------------
# A ledger written in an OLD SHAPE. Same type, same name, different meaning:
# a key that has already spent nine of its ten, and a limit the app learned
# the hard way. If the upgrade resets either, a day's budget is lost or, worse,
# spent twice.
DAY="$(TZ=America/Los_Angeles date +%Y-%m-%d)"
cat > "$APPHOME/ledger.json" <<LEDGER_EOF
{
 "day": "$DAY",
 "spend": {"old label|gemini-2.5-flash-preview-tts": 9},
 "seen": {"gemini-2.5-flash-preview-tts": {"rpd": 10, "rpm": 3}},
 "audio_out": 411.5,
 "audio_in": 96.0,
 "dead": {"a dead one": "401"}
}
LEDGER_EOF
mkdir -p "$APPHOME/out"
printf 'RIFF....WAVEfake' > "$APPHOME/out/speak_before_upgrade.wav"
printf 'my own note\n' > "$APPHOME/notes.txt"

# a key imported by the OLD version, which the new one must not lose and must
# not import a second time when the same file is handed over again
IMPKEY="AQ.Ab8RN6UPGRADEUPGRADEUPGRADEUPGRADE"
printf 'imported before the upgrade\n%s\n' "$IMPKEY" > "$SANDBOX/oldimport.txt"
"$PY" "$APPHOME/app.py" import "$SANDBOX/oldimport.txt" >/dev/null 2>&1
# something in the graveyard, which the upgrade must not lose either
mkdir -p "$APPHOME"
printf '# refused, before the upgrade\na deleted one\nAQ.Ab8RN6GRAVEGRAVEGRAVEGRAVEGRAV\n\n' > "$APPHOME/removed_keys"
KEYSUM_BEFORE="$(cksum < "$HOME/.gemini_keys")"
grep -q "$IMPKEY" "$HOME/.gemini_keys" && ok "the old version imported a key" \
  || bad "the old version imported a key"

# --- 3. leave it running ---------------------------------------------------
# Started the way the launcher starts it, absolute path and all. A test that
# starts it differently proves nothing about the real thing.
# A fixed port made this test fail when a previous run left a server behind:
# the new one exited "address already in use" and the check read that as the
# old server having died. Ask the operating system for a free one instead.
TESTPORT="$("$PY" -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()")"
GTTS_PORT="$TESTPORT" GEMINI_KEYS="$HOME/.gemini_keys" "$PY" "$APPHOME/app.py" > "$SANDBOX/server.log" 2>&1 &
OLDPID=$!
sleep 3
if kill -0 "$OLDPID" 2>/dev/null; then ok "the old server is running during the upgrade"
else bad "the old server is running during the upgrade"; fi

# --- 4. install on top -----------------------------------------------------
OUTPUT="$(bash "$INSTALLER" --quiet 2>&1)"
RC=$?
want "the upgrade exits clean" "$RC" "0"

# --- 5. check everything ---------------------------------------------------
want "the key file is byte for byte the same" "$(cksum < "$HOME/.gemini_keys")" "$KEYSUM_BEFORE"
want "a key deleted before the upgrade is still recoverable after it" \
     "$(grep -c 'AQ.Ab8RN6GRAVEGRAVEGRAVEGRAVEGRAV' "$APPHOME/removed_keys" 2>/dev/null || true)" "1"
want "the key file is still 600" "$(ls -l "$HOME/.gemini_keys" | cut -c1-10)" "-rw-------"

L="$APPHOME/ledger.json"
want "the ledger survived"            "$(grep -c 'old label' "$L")" "1"
want "the spend keeps its VALUE, not its default" \
     "$($PY -c "import json;print(json.load(open('$L'))['spend']['old label|gemini-2.5-flash-preview-tts'])")" "9"
want "what the app learned about the daily limit survived" \
     "$($PY -c "import json;print(json.load(open('$L'))['seen']['gemini-2.5-flash-preview-tts']['rpd'])")" "10"
want "the seconds already made are still counted" \
     "$($PY -c "import json;print(json.load(open('$L'))['audio_out'])")" "411.5"
want "a key marked dead stays dead" \
     "$($PY -c "import json;print('a dead one' in json.load(open('$L'))['dead'])")" "True"

[ -f "$APPHOME/out/speak_before_upgrade.wav" ] && ok "audio made by the old version is still there" \
  || bad "audio made by the old version is still there"
[ -f "$APPHOME/notes.txt" ] && ok "a file the installer knows nothing about is untouched" \
  || bad "a file the installer knows nothing about is untouched"

# every executable replaced, including the one that was running
grep -q "gtt-update" "$BIN/gtt-update" && ok "gtt-update was rewritten" || bad "gtt-update was rewritten"
[ -x "$BIN/gtt" ] && ok "gtt is still executable" || bad "gtt is still executable"
[ ! -f "$BIN/gtt.new" ] && [ ! -f "$BIN/gtt-update.new" ] && [ ! -f "$APPHOME/app.py.new" ] \
  && ok "no half written .new file was left behind" || bad "no half written .new file was left behind"

# the same file handed to the NEW version must add nothing
NEWOUT="$("$PY" "$APPHOME/app.py" import "$SANDBOX/oldimport.txt" 2>&1)"
COUNT="$(grep -c "$IMPKEY" "$HOME/.gemini_keys")"
want "a key imported before the upgrade is not imported again" "$COUNT" "1"
printf '%s' "$NEWOUT" | grep -q "already in the ring" \
  && ok "and the new version says it is already there" \
  || bad "and the new version says it is already there"

# the rename rule, tested for what it actually protects: a script being READ
# by a running shell must survive being replaced mid-read.
cat > "$SANDBOX/victim.sh" <<'VICTIM_EOF'
sleep 2
echo "SECOND HALF STILL READ"
VICTIM_EOF
( bash "$SANDBOX/victim.sh" > "$SANDBOX/victim.out" 2>&1 ) &
VPID=$!
sleep 0.5
printf 'echo REPLACED\n' > "$SANDBOX/victim.new"
mv -f "$SANDBOX/victim.new" "$SANDBOX/victim.sh"
wait $VPID 2>/dev/null
grep -q "SECOND HALF STILL READ" "$SANDBOX/victim.out" \
  && ok "a rename does not disturb a shell reading the file" \
  || bad "a rename does not disturb a shell reading the file"

# doing it a second time changes nothing
cksum < "$L" > "$SANDBOX/l1"
bash "$INSTALLER" --quiet >/dev/null 2>&1
cksum < "$L" > "$SANDBOX/l2"
cmp -s "$SANDBOX/l1" "$SANDBOX/l2" && ok "installing a third time changes nothing" \
  || bad "installing a third time changes nothing"

# THE EMPTY RING BRANCH. This is what "1 of 4 green" on a fresh phone was:
# grep -c prints 0 and exits 1, so `|| echo 0` made the count "0\n0", the
# numeric test errored, and the installer ran the gate against no keys at all.
EMPTY="$(mktemp -d)"
HOME="$EMPTY" bash "$INSTALLER" > "$EMPTY/out.txt" 2>&1
grep -q "No keys yet" "$EMPTY/out.txt" \
  && ok "an install with no keys says so" || bad "an install with no keys says so"
grep -q "of 4 green" "$EMPTY/out.txt" \
  && bad "an install with no keys must NOT run the provider tests" \
  || ok "an install with no keys does not run the provider tests"
grep -q "a test failed" "$EMPTY/out.txt" \
  && bad "an install with no keys must not report a failure" \
  || ok "an install with no keys does not report a failure"
[ -x "$EMPTY/bin/gtts" ] && ok "gtts is installed beside gtt" || bad "gtts is installed beside gtt"
# gtt with no argument must START the app, not sit at a menu waiting for a key
# press. v5 sat, and on an empty ring it refused to start at all, which put the
# picker that fixes an empty ring behind the empty ring.
grep -q 'exec "\$PY" "\$APP"$' "$EMPTY/bin/gtt" \
  && ok "gtt with no argument runs the app" || bad "gtt with no argument runs the app"
grep -q 'menu)   MENU=1' "$EMPTY/bin/gtt" \
  && ok "the panel is still reachable as gtt menu" || bad "the panel is still reachable as gtt menu"

# EVERY LABEL IS SPELLED BY ITS OWN KEY. The row is meant to be recognised
# rather than read, and a letter that does not begin its word has to be read.
# This checks the drawn row and the case arm agree, letter by letter, so a
# label cannot be reworded later without its key moving with it.
ROWFAIL=""
for pair in "R:un" "T:est" "K:eys" "O:utput" "U:pdate" "I:mport" "Q:uit"; do
  L="${pair%%:*}"; W="${pair#*:}"
  l="$(printf '%s' "$L" | tr 'A-Z' 'a-z')"
  # the letter is drawn immediately before the rest of its own word
  grep -q "}$L\${OFF} $W" "$EMPTY/bin/gtt" || ROWFAIL="$ROWFAIL $L-label"
  # and that same letter is the arm that runs it
  grep -q "$l|$L|" "$EMPTY/bin/gtt" || ROWFAIL="$ROWFAIL $L-key"
done
[ -z "$ROWFAIL" ] && ok "every action key spells its own word" \
  || bad "every action key spells its own word:$ROWFAIL"
grep -qE '^ *[0-9] (run|test|keys|output|update|import|quit)' "$EMPTY/bin/gtt" \
  && bad "the numbered labels are gone from the drawn row" \
  || ok "the numbered labels are gone from the drawn row"
grep -q 'r|R|1)' "$EMPTY/bin/gtt" \
  && ok "but the old numbers still work for fingers that learned them" \
  || bad "but the old numbers still work for fingers that learned them"
if [ -x "$EMPTY/bin/gtts" ]; then
  HOME="$EMPTY" "$EMPTY/bin/gtts" out >/dev/null 2>&1 \
    && ok "gtts runs the same thing as gtt" || bad "gtts runs the same thing as gtt"
fi
HOME="$EMPTY" "$PY" "$EMPTY/.google_tts_stt/app.py" test > "$EMPTY/t.txt" 2>&1
grep -q "ring is empty" "$EMPTY/t.txt" \
  && ok "gtt test on an empty ring says why, once" \
  || bad "gtt test on an empty ring says why, once"
rm -rf "$EMPTY"

# INSTALLING MUST NOT SPEND A KEY. This is the sharpest one on the list: the
# four tests make real calls, a TTS account has ten a day, and an install that
# quietly takes some of them has decided something on the person's behalf.
SPEND="$(mktemp -d)"
printf 'a key\nAQ.Ab8RN6SPENDCHECKSPENDCHECKSPE\n' > "$SPEND/.gemini_keys"
HOME="$SPEND" bash "$INSTALLER" > "$SPEND/out.txt" 2>&1
grep -q "of 4 green" "$SPEND/out.txt" \
  && bad "an install with keys in the ring must still not test them" \
  || ok "an install with keys in the ring does not test them"
grep -qi "no mocks" "$SPEND/out.txt" \
  && bad "and does not announce a test run" || ok "and does not announce a test run"
[ -f "$SPEND/.google_tts_stt/ledger.json" ] \
  && bad "and writes no ledger, because it spent nothing" \
  || ok "and writes no ledger, because it spent nothing"
HOME="$SPEND" bash "$INSTALLER" --test > "$SPEND/out2.txt" 2>&1
grep -q "because you asked" "$SPEND/out2.txt" \
  && ok "--test still runs them, because asking is different" \
  || bad "--test still runs them, because asking is different"
rm -rf "$SPEND"

# THE VENDORED APP. It must arrive whole, and it must arrive with its engine
# swapped: shipping the upstream page untouched would leave it calling
# AssemblyAI with keys it does not have.
T="$APPHOME/transcribe.html"
[ -f "$T" ] && ok "the Maha Transcribe page is installed" || bad "the Maha Transcribe page is installed"
if [ -f "$T" ]; then
  SZ=$(wc -c < "$T")
  [ "$SZ" -gt 100000 ] && ok "and it is the whole app, not a stub ($SZ bytes)" \
    || bad "and it is the whole app, not a stub ($SZ bytes)"
  grep -q "fetch('/api/listen'" "$T" \
    && ok "the engine is this server" || bad "the engine is this server"
  grep -q "return aaiTranscribe(blob, filename, statusFn);" "$T" \
    && bad "the upstream dispatch must be gone" || ok "the upstream dispatch is gone"
  grep -q "aaiAttemptJob" "$T" \
    && ok "but the rest of the app is untouched, not rewritten" \
    || bad "but the rest of the app is untouched, not rewritten"
fi

# the generated installer must match its sources
if $PY "$ROOT/tools/build_installer.py" --check >/dev/null 2>&1; then
  ok "the shipped installer matches src/"
else
  bad "the shipped installer is stale, rebuild it"
fi

kill "$OLDPID" 2>/dev/null
wait "$OLDPID" 2>/dev/null
rm -rf "$SANDBOX"

printf "\nTEST 4: %d checks, %d failed\n" "$((PASS+FAIL))" "$FAIL"
printf "        NOT tested: an upgrade from a genuinely older release, because\n"
printf "        there is not one yet. From v2 this test uses the real thing.\n"
[ "$FAIL" -eq 0 ]
