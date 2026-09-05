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
