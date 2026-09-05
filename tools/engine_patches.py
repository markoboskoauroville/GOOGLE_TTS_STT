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
