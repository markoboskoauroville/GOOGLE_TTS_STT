"""
The engine seam for the vendored Maha Transcribe page.

`src/30_transcribe.html` is MAHA_TRANSCRIBE_TERMUX_TERMINAL/maha_transcribe.html,
byte for byte. The app is not reimplemented and not redesigned: the recording,
the queue, the archive, the correction, the translation, the settings, all of it
is the app Baba already uses.

ONLY THE ENGINE CHANGES. Upstream transcribes with AssemblyAI, from keys the
browser keeps in localStorage. Here it transcribes with Gemini, through this
app's own server, so the keys never reach the page and the rotation, the ledger
and the daily budget cover transcription like everything else.

Three anchors, because the upstream app already has exactly one dispatch point
and one readiness check. Replacing more than this would be rewriting somebody
else's app rather than changing its engine. A missing anchor is fatal at build
time: silently shipping the upstream page would leave it calling AssemblyAI.
"""

DISPATCH_OLD = """  // ---- assemblyai is the only transcription service ----
  function transcribeDispatch(blob, filename, statusFn) {
    return aaiTranscribe(blob, filename, statusFn);
  }"""

DISPATCH_NEW = """  // ---- GEMINI, through this app own server ----
  // The one seam. Upstream this called aaiTranscribe and the browser held the
  // keys. Here the blob goes to /api/listen and the server ring answers it, so
  // the keys stay on disk and the same fallback, ledger and daily budget cover
  // transcription too. Everything above and below this function is untouched.
  async function transcribeDispatch(blob, filename, statusFn) {
    const gen = txCancelGen;
    statusFn('gemini  \\u00b7  sending ' + Math.round(blob.size / 1024) + ' KB');
    try {
      const fd = new FormData();
      fd.append('audio', blob, filename || 'audio.webm');
      const lang = activeLang();
      fd.append('lang', lang === 'hr' ? 'Croatian' : (lang === 'en' ? 'English' : ''));
      const r = await fetch('/api/listen', { method: 'POST',
        headers: { 'X-Gtt-Local': '1' }, body: fd });
      if (txCanceled(gen)) return null;
      const j = await r.json();
      if (!j.ok) { statusFn('gemini: ' + (j.error || 'failed'), 'err'); return null; }
      statusFn('gemini  \\u00b7  ' + j.seconds + 's heard on [' + j.key + ']');
      return (j.text || '').trim();
    } catch (e) {
      statusFn('gemini: ' + e.message, 'err');
      return null;
    }
  }"""

READY_OLD = """  function serviceReady() { return ringHasKeys('assembly'); }"""

READY_NEW = """  // The ring belongs to the server now, so readiness is a question for it.
  // Optimistic until told otherwise: a page that greys itself out while one
  // fetch is in flight is a page that jumps.
  let __ringHasKeys = true;
  fetch('/api/health', { headers: { 'X-Gtt-Local': '1' } })
    .then(r => r.json())
    .then(h => {
      __ringHasKeys = h.keys > 0;
      if (!h.keys) setStatus('no keys yet, open the KEYS tab and pick your key file', 'err');
    })
    .catch(() => {});
  function serviceReady() { return __ringHasKeys; }"""

MSG_OLD = """  if (!serviceReady()) setStatus('no assemblyai keys, check settings', 'err');"""
MSG_NEW = """  // the message now comes from the health check above, once it answers"""

PATCHES = [(DISPATCH_OLD, DISPATCH_NEW), (READY_OLD, READY_NEW), (MSG_OLD, MSG_NEW)]


# ---------------------------------------------------------------- ONE ENGINE
#
# Baba, 5.9.2026: "we said change the engine, but there are so many other
# engines. We need from this app only recording and transcribe. Translate goes
# out. Gemini models, you need to choose them automatically."
#
# So the choosing goes. Every one of these takes something OUT rather than
# adding: the translate pill, the Claude/Gemini switch, the Claude model list,
# the Claude budget, the Gemini correction model list, the AssemblyAI model
# list, and every per-provider key panel. What is left is record, transcribe,
# correct, and one place the keys live.
#
# A model list in a settings panel is a list that goes stale, and a dated model
# name is a time bomb: it fails with not_found before the request runs, so it
# never shows in usage and looks exactly like a dead key. modules/model-names.md.

DROP_TRANSLATE_OLD = '    <button class="tab-btn" data-tab="translate">translate</button>\n'

DROP_TRANSLATE_NEW = ''

SETTINGS_OLD = '    <label class="field-label">reshape and grammar model</label>\n    <div class="row" id="corrProviderList" style="flex-wrap:wrap;"></div>\n    <label class="field-label">claude api model</label>\n    <div class="row" id="claudeModelList" style="flex-wrap:wrap;"></div>\n    <label class="field-label">claude session budget (usd)</label>\n    <input type="number" step="0.5" min="0.5" id="claudeBudget" class="text-input" />\n    <label class="field-label">gemini correction model</label>\n    <div class="row" id="corrModelList" style="flex-wrap:wrap;"></div>\n    <label class="field-label">assemblyai transcription model</label>\n    <div class="row" id="aaiModelList" style="flex-wrap:wrap;"></div>\n    <label class="field-label">api keys</label>\n    <div class="key-list">\n      no key is stored in this file. keys live only in this browser, imported by you below.\n    </div>\n    <div id="keyringPanels"></div>'

SETTINGS_NEW = '    <label class="field-label">engine</label>\n    <div class="key-list">\n      Gemini, and the model is chosen for you from the ones the account can\n      actually reach. There is nothing to pick here and nothing to keep current.\n    </div>\n    <label class="field-label">api keys</label>\n    <div class="key-list">\n      The keys are not in this browser. They live in one ring on the server,\n      shared with the rest of this app, and the KEYS tab is where they are\n      imported, tested and deleted.\n    </div>'

ABOUT_OLD = '    <div class="about">\n      assembly models: <b>universal-3-pro, universal-2</b><br>\n      reshape/grammar: <b>claude or gemini</b><br>\n      file picker: <b>any format ffmpeg can read, optimized before upload</b><br>\n      version: <b id="appVersion">v28 (a)</b>\n    </div>'

ABOUT_NEW = '    <div class="about">\n      engine: <b>Gemini, model chosen automatically</b><br>\n      keys: <b>the shared ring, in the KEYS tab</b><br>\n      file picker: <b>any format ffmpeg can read, optimized before upload</b><br>\n      version: <b id="appVersion">v28 (a)</b>\n    </div>'

CORRECTION_OLD = "  async function runCorrection(kind) {\n    const text = (transcriptEl.value || '').trim();\n    if (!text) { setGrammarStatus('the transcript box is empty', 'err'); return; }\n    const provider = getCorrProvider();\n    const prompt = kind === 'grammar' ? GRAMMAR_PROMPT : RESHAPE_PROMPT;\n    const verb = kind === 'grammar' ? 'correcting' : 're-shaping';\n    grammarBtn.disabled = true; reshapeBtn.disabled = true; setMeter('busy');\n    if (provider === 'claude') {\n      const name = CLAUDE_MODELS[getClaudeModel()].name;\n      const effort = getClaudeEffort();\n      setGrammarStatus(verb + ' with Claude ' + name + ' ' + effort);\n      const res = await claudeGenerate(prompt + text.slice(0, 200000), effort, setGrammarStatus);\n      if (res) { transcriptCorr.value = res.text; setMeter('ok'); setGrammarStatus('done  \\u00b7  Claude ' + name + ' ' + effort + '  \\u00b7  this call $' + res.cost.toFixed(4), 'ok'); bumpUsage('corr'); }\n      else { setMeter('err'); }\n    } else {\n      if (!ringHasKeys('gemini')) { setGrammarStatus('no gemini keys', 'err'); setMeter('err'); grammarBtn.disabled = false; reshapeBtn.disabled = false; return; }\n      const model = getQModel();\n      setGrammarStatus(verb + ' with Gemini ' + model);\n      const res = await geminiGenerate(prompt + text.slice(0, 60000), model, setGrammarStatus);\n      if (res) { transcriptCorr.value = res.text; setMeter('ok'); setGrammarStatus('done  \\u00b7  Gemini ' + model + ', key ' + maskKey(res.key), 'ok'); bumpUsage('corr'); }\n      else { setMeter('err'); }\n    }\n    grammarBtn.disabled = false; reshapeBtn.disabled = false; setTimeout(() => setMeter('idle'), 1600);\n  }\n"

CORRECTION_NEW = "  // ONE ENGINE. Upstream this chose between Claude and Gemini, then a model\n  // within whichever was chosen, and a spend budget for one of them. All of\n  // that is gone: the server picks from the models the ring can actually reach\n  // and answers on /api/rewrite. A model list in a settings panel is a list\n  // that goes stale, and a dated model name is a time bomb that fails before\n  // the request runs.\n  async function runCorrection(kind) {\n    const text = (transcriptEl.value || '').trim();\n    if (!text) { setGrammarStatus('the transcript box is empty', 'err'); return; }\n    const verb = kind === 'grammar' ? 'correcting' : 're-shaping';\n    grammarBtn.disabled = true; reshapeBtn.disabled = true; setMeter('busy');\n    setGrammarStatus(verb + '\\u2026');\n    try {\n      const r = await fetch('/api/rewrite', {\n        method: 'POST',\n        headers: { 'Content-Type': 'application/json', 'X-Gtt-Local': '1' },\n        body: JSON.stringify({ kind: kind, text: text.slice(0, 60000) })\n      });\n      const j = await r.json();\n      if (j.ok) {\n        transcriptCorr.value = j.text;\n        setMeter('ok');\n        setGrammarStatus('done  \\u00b7  ' + j.model + ' on [' + j.key + ']', 'ok');\n        bumpUsage('corr');\n      } else {\n        setMeter('err');\n        setGrammarStatus(j.error || 'failed', 'err');\n      }\n    } catch (e) {\n      setMeter('err'); setGrammarStatus(e.message, 'err');\n    }\n    grammarBtn.disabled = false; reshapeBtn.disabled = false;\n    setTimeout(() => setMeter('idle'), 1600);\n  }\n"

PATCHES += [(DROP_TRANSLATE_OLD, DROP_TRANSLATE_NEW), (SETTINGS_OLD, SETTINGS_NEW), (ABOUT_OLD, ABOUT_NEW), (CORRECTION_OLD, CORRECTION_NEW)]


# Two renderers that wrote straight into elements the strip above removed. A
# null.innerHTML throws, and it throws during setup, which would take the whole
# page down rather than just its settings panel. Guarded rather than deleted:
# each is called from several places.
GUARD0_OLD = '  function renderAaiModels() {\n    const cur = getAaiModel();'

GUARD0_NEW = '  function renderAaiModels() {\n    // the AssemblyAI picker is gone from settings, so this element is not\n    // there any more. Guard rather than delete: the function is called from\n    // several places and a null.innerHTML throws before any of them run.\n    if (!aaiModelList) return;\n    const cur = getAaiModel();'

GUARD1_OLD = '  function renderCorrModels() {\n    const cur = getQModel();'

GUARD1_NEW = '  function renderCorrModels() {\n    // likewise: the model is chosen by the server now, so there is no list\n    if (!corrModelList) return;\n    const cur = getQModel();'

PATCHES += [(GUARD0_OLD, GUARD0_NEW), (GUARD1_OLD, GUARD1_NEW)]


RINGHAS_OLD = '  function ringHasKeys(provider) { return loadRing(provider).keys.length > 0; }'

RINGHAS_NEW = "  // THE RING IS THE SERVER'S. Upstream every gate asked localStorage whether\n  // this browser held keys for a provider, and there are none here: the keys\n  // live in one file on the server now. serviceReady() was patched and these\n  // four were not, so the RECORD to transcribe button stayed disabled forever\n  // and a recording could never be transcribed - which also made SINGLE and\n  // MULTIPLE look broken, because the mode only shows in what the session does\n  // with a transcript it was never allowed to fetch.\n  //\n  // Optimistic until told otherwise: a page that greys itself out while one\n  // fetch is in flight is a page that jumps.\n  let __serverKeys = 1;\n  function refreshServerKeys() {\n    fetch('/api/health', { headers: { 'X-Gtt-Local': '1' } })\n      .then(r => r.json())\n      .then(h => {\n        __serverKeys = h.keys || 0;\n        if (typeof updateRecTranscribeState === 'function') updateRecTranscribeState();\n        if (typeof updateTranscribeState === 'function') updateTranscribeState();\n      })\n      .catch(() => {});\n  }\n  function ringHasKeys(provider) { return __serverKeys > 0; }"

MICBEST_OLD = "    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {\n      recStream = stream;\n      takeId = Date.now();\n      segIndex = 0;\n      takeSegments = [];\n      recMime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';"

MICBEST_NEW = "    // RECORD AT THE BEST THE PHONE WILL GIVE. The processing that makes a\n    // phone call intelligible - AGC, noise suppression, echo cancellation -\n    // is tuned for a human on the other end, and it removes exactly the quiet\n    // detail a transcriber needs. Off, and let ffmpeg do the reduction later\n    // from a clean source.\n    navigator.mediaDevices.getUserMedia({\n      audio: {\n        channelCount: 1,\n        sampleRate: 48000,\n        echoCancellation: false,\n        noiseSuppression: false,\n        autoGainControl: false\n      }\n    }).catch(() => navigator.mediaDevices.getUserMedia({ audio: true }))\n      .then(stream => {\n      recStream = stream;\n      takeId = Date.now();\n      segIndex = 0;\n      takeSegments = [];\n      // Chrome and Brave record webm/opus. FIREFOX DOES NOT: it produces\n      // ogg/opus and returns false for every webm type, so a webm-only list\n      // leaves it with the empty string and a recorder that never starts.\n      recMime = '';\n      ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm',\n       'audio/ogg', 'audio/mp4'].some(function (m) {\n        if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) {\n          recMime = m;\n          return true;\n        }\n        return false;\n      });"

RECBITS_OLD = '    mediaRecorder = new MediaRecorder(recStream, { mimeType: recMime });'

RECBITS_NEW = '    // 128 kbps into the recorder. It costs nothing that matters - the file\n    // lives on this phone for seconds before ffmpeg reduces it - and it is the\n    // difference between reducing FROM a clean source and reducing from one\n    // that has already been thinned once.\n    mediaRecorder = recMime\n      ? new MediaRecorder(recStream, { mimeType: recMime, audioBitsPerSecond: 128000 })\n      : new MediaRecorder(recStream, { audioBitsPerSecond: 128000 });'

PREPALL_OLD = "  async function transcribeSegmentsSeq(segments, statusFn) {\n    const parts = [];\n    for (let i = 0; i < segments.length; i++) {\n      const label = segments.length > 1 ? ('segment ' + (i + 1) + '/' + segments.length + '  \\u00B7  ') : '';\n      const t = await transcribeDispatch(segments[i], 'segment_' + (i + 1) + '.webm', (m) => statusFn(label + m));"

PREPALL_NEW = "  // EVERY transcription passes through ffmpeg, recordings included. The file\n  // picker already did; a recording used to go straight up as whatever the\n  // browser happened to produce, which is a different pipeline for the same\n  // job and the one nobody was testing.\n  async function prepForUpload(blob, statusFn) {\n    try {\n      const fd = new FormData();\n      fd.append('file', blob, 'take.webm');\n      const r = await fetch('/api/optimize-audio', {\n        method: 'POST', headers: { 'X-Gtt-Local': '1' }, body: fd\n      });\n      if (!r.ok) return blob;                       // reduce if we can, send if we cannot\n      const out = await r.blob();\n      if (!out || !out.size) return blob;\n      if (statusFn) statusFn('optimized  \\u00B7  ' + Math.round(blob.size / 1024) +\n                             ' KB \\u2192 ' + Math.round(out.size / 1024) + ' KB');\n      return out;\n    } catch (e) {\n      return blob;\n    }\n  }\n\n  async function transcribeSegmentsSeq(segments, statusFn) {\n    const parts = [];\n    for (let i = 0; i < segments.length; i++) {\n      const label = segments.length > 1 ? ('segment ' + (i + 1) + '/' + segments.length + '  \\u00B7  ') : '';\n      const ready = await prepForUpload(segments[i], (m) => statusFn(label + m));\n      const t = await transcribeDispatch(ready, 'segment_' + (i + 1) + '.ogg', (m) => statusFn(label + m));"

PATCHES += [(RINGHAS_OLD, RINGHAS_NEW), (MICBEST_OLD, MICBEST_NEW), (RECBITS_OLD, RECBITS_NEW), (PREPALL_OLD, PREPALL_NEW)]


# ------------------------------------------------------------ STAGED STATUS
#
# Baba: "I want to see this app being alive nonstop and informing me what it
# does in every of its windows."
#
# The three stages that take real time are transcoding, sending and waiting,
# and silence during any of them is indistinguishable from a stall. Each one
# now says its own name, in this page's status line AND to the page around it:
# this page runs in an iframe, and the activity line in the parent should say
# what the app is doing whichever tab is being looked at.
#
# Applied to the replacements above BY VALUE rather than written into them by
# hand. Those literals already carry escaped JavaScript, and editing escaped
# text inside an escaped literal is exactly what shipped a dead page at v13.

_ACT_HELPER = """  function gttAct(msg, done) {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ gtt: 'act', msg: msg, done: !!done }, '*');
      }
    } catch (ignored) {}
  }

"""


def _stage(new):
    """Return the replacement with its stages announced."""
    out = _ACT_HELPER + new

    # sending
    out = out.replace(
        "statusFn('gemini  \\u00b7  sending ' + Math.round(blob.size / 1024) + ' KB');",
        "const kb = Math.round(blob.size / 1024);\n"
        "    statusFn('sending ' + kb + ' KB to Google\\u2026');\n"
        "    gttAct('sending ' + kb + ' KB to Google');")

    # waiting, with a second counter, because a silent minute reads as a hang
    out = out.replace(
        "      const r = await fetch('/api/listen', { method: 'POST',\n"
        "        headers: { 'X-Gtt-Local': '1' }, body: fd });",
        "      const t0 = Date.now();\n"
        "      const tick = setInterval(function () {\n"
        "        const s = Math.round((Date.now() - t0) / 1000);\n"
        "        statusFn('waiting for Google\\u2026  ' + s + 's');\n"
        "        gttAct('waiting for Google, ' + s + 's');\n"
        "      }, 1000);\n"
        "      let r;\n"
        "      try {\n"
        "        r = await fetch('/api/listen', { method: 'POST',\n"
        "          headers: { 'X-Gtt-Local': '1' }, body: fd });\n"
        "      } finally { clearInterval(tick); }")

    # receiving, and an empty transcript that used to read as success
    out = out.replace(
        "      const j = await r.json();\n"
        "      if (!j.ok) { statusFn('gemini: ' + (j.error || 'failed'), 'err'); return null; }\n"
        "      statusFn('gemini  \\u00b7  ' + j.seconds + 's heard on [' + j.key + ']');\n"
        "      return (j.text || '').trim();",
        "      statusFn('receiving\\u2026');\n"
        "      gttAct('receiving the transcript');\n"
        "      const j = await r.json();\n"
        "      if (!j.ok) {\n"
        "        statusFn('Google: ' + (j.error || 'failed'), 'err');\n"
        "        gttAct('Google refused: ' + (j.error || 'failed'), true);\n"
        "        return null;\n"
        "      }\n"
        "      const text = (j.text || '').trim();\n"
        "      if (!text) {\n"
        "        statusFn('Google heard ' + j.seconds + 's and returned no words', 'err');\n"
        "        gttAct('no words came back', true);\n"
        "        return null;\n"
        "      }\n"
        "      statusFn('done  \\u00b7  ' + j.seconds + 's heard, ' + j.model +\n"
        "               ' on [' + j.key + ']', 'ok');\n"
        "      gttAct('done, ' + j.seconds + 's transcribed', true);\n"
        "      return text;")

    out = out.replace(
        "      statusFn('gemini: ' + e.message, 'err');\n      return null;",
        "      statusFn('Google: ' + e.message, 'err');\n"
        "      gttAct('that did not go through: ' + e.message, true);\n"
        "      return null;")

    # transcoding
    out = out.replace(
        "      fd.append('file', blob, 'take.webm');",
        "      fd.append('file', blob, 'take.webm');\n"
        "      const before = Math.round(blob.size / 1024);\n"
        "      if (statusFn) statusFn('transcoding ' + before + ' KB with ffmpeg\\u2026');\n"
        "      gttAct('transcoding ' + before + ' KB with ffmpeg');")
    out = out.replace("statusFn('optimized  \\u00b7  '", "statusFn('transcoded  \\u00b7  '")
    return out


_staged = []
for _old, _new in PATCHES:
    if "transcribeDispatch(blob, filename, statusFn)" in _new or "prepForUpload" in _new:
        _staged.append((_old, _stage(_new)))
    else:
        _staged.append((_old, _new))
PATCHES = _staged
