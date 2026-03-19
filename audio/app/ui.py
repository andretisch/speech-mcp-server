def debug_html() -> str:
    # Keep UI as a single string for simplicity.
    # (Copied from previous server.py with minimal changes.)
    return """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>STT + TTS Debug</title>
    <style>
      :root { --bg:#0b1020; --muted:#8aa0c7; --text:#e6efff; --danger:#ff6a8b; --ok:#46d39a; --border:rgba(255,255,255,.10); }
      * { box-sizing: border-box; }
      body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        background: radial-gradient(1200px 800px at 20% 0%, rgba(106,169,255,.25), transparent 55%),
                    radial-gradient(900px 650px at 100% 10%, rgba(70,211,154,.18), transparent 60%), var(--bg);
        color: var(--text); }
      .wrap { max-width: 1100px; margin:0 auto; padding:20px; }
      .top { display:flex; gap:14px; align-items:baseline; justify-content:space-between; margin-bottom:14px; }
      h1 { margin:0; font-size:20px; font-weight:650; }
      .pill { display:inline-flex; gap:8px; align-items:center; padding:6px 10px; border:1px solid var(--border); border-radius:999px;
        background: rgba(18,26,51,.6); color: var(--muted); font-size:12px; }
      .dot { width:8px; height:8px; border-radius:999px; background: rgba(255,255,255,.25); }
      .dot.ok { background: var(--ok); } .dot.bad { background: var(--danger); }
      .grid { display:grid; grid-template-columns: 1fr 1fr; gap:14px; }
      @media (max-width:900px){ .grid{ grid-template-columns:1fr; } }
      .card { background: rgba(18,26,51,.82); border:1px solid var(--border); border-radius:14px; padding:14px; box-shadow: 0 18px 60px rgba(0,0,0,.35); }
      .card h2 { margin:0 0 10px 0; font-size:14px; color: var(--muted); font-weight:650; }
      label { display:block; font-size:12px; color: var(--muted); margin:10px 0 6px; }
      input[type="file"], textarea, select { width:100%; border:1px solid var(--border); background: rgba(11,16,32,.55); color: var(--text);
        border-radius:10px; padding:10px 11px; outline:none; }
      textarea { min-height:140px; resize:vertical; line-height:1.3; }
      .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
      button { border:1px solid rgba(106,169,255,.35); background: linear-gradient(180deg, rgba(106,169,255,.22), rgba(106,169,255,.10));
        color: var(--text); padding:9px 12px; border-radius:10px; cursor:pointer; font-weight:650; }
      button.secondary { border:1px solid var(--border); background: rgba(11,16,32,.45); color: var(--muted); font-weight:600; }
      button:disabled { opacity:.55; cursor:not-allowed; }
      .hint { font-size:12px; color: var(--muted); margin-top:8px; }
      .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }
      .log { margin-top:10px; padding:10px; border-radius:10px; border:1px solid var(--border); background: rgba(11,16,32,.55);
        white-space: pre-wrap; word-break: break-word; font-size:12px; min-height:84px; }
      audio { width:100%; margin-top:10px; }
      .small { font-size:11px; color: var(--muted); }
      .split { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }
      @media (max-width:620px){ .split{ grid-template-columns:1fr; } }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="top">
        <h1>STT + TTS Debug</h1>
        <div class="pill" title="GET /health">
          <span id="healthDot" class="dot"></span>
          <span id="healthText">health: …</span>
          <span class="mono" id="deviceText"></span>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <h2>STT — распознавание</h2>
          <label for="sttFile">Аудио файл</label>
          <input id="sttFile" type="file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm" />
          <div class="row" style="margin-top: 10px;">
            <button id="btnTranscribe">Transcribe</button>
            <button id="btnTranscribeClear" class="secondary">Очистить</button>
            <span class="small">POST <span class="mono">/transcribe</span> (multipart поле <span class="mono">file</span>)</span>
          </div>
          <label for="sttText">Результат</label>
          <textarea id="sttText" placeholder="Тут появится распознанный текст…"></textarea>
          <div class="hint">Ниже — сегменты diarization (speaker + time):</div>
          <div class="log mono" id="sttSegments" style="min-height: 120px;"></div>
        </div>

        <div class="card">
          <h2>TTS — синтез (Silero)</h2>
          <label for="ttsMode">Режим</label>
          <select id="ttsMode">
            <option value="auto" selected>auto (RU+EN)</option>
            <option value="ru">ru (только русский)</option>
            <option value="en">en (только английский)</option>
          </select>
          <label for="ttsText">Текст</label>
          <textarea id="ttsText" placeholder="Введи текст для озвучки…"></textarea>
          <div class="row" style="margin-top: 10px;">
            <button id="btnSpeak">Speak</button>
            <button id="btnUseStt" class="secondary">Взять из STT</button>
            <button id="btnTtsClear" class="secondary">Очистить</button>
            <span class="small">POST <span class="mono">/api/tts</span> (JSON)</span>
          </div>
          <audio id="ttsAudio" controls></audio>
        </div>

        <div class="card" style="grid-column: 1 / -1;">
          <h2>Лог</h2>
          <div class="split">
            <div>
              <div class="small">Короткие команды для терминала</div>
              <div class="log mono" id="snippets"></div>
            </div>
            <div>
              <div class="small">События страницы</div>
              <div class="log mono" id="log"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <script>
      const $ = (id) => document.getElementById(id);
      const logEl = $("log");
      const snippetsEl = $("snippets");
      const healthDot = $("healthDot");
      const healthText = $("healthText");
      const deviceText = $("deviceText");
      const sttFile = $("sttFile");
      const sttText = $("sttText");
      const sttSegments = $("sttSegments");
      const ttsMode = $("ttsMode");
      const ttsText = $("ttsText");
      const ttsAudio = $("ttsAudio");
      const btnTranscribe = $("btnTranscribe");
      const btnTranscribeClear = $("btnTranscribeClear");
      const btnSpeak = $("btnSpeak");
      const btnUseStt = $("btnUseStt");
      const btnTtsClear = $("btnTtsClear");

      function now() { return new Date().toISOString().replace("T", " ").replace("Z", ""); }
      function appendLog(line) { logEl.textContent += `[${now()}] ${line}\\n`; logEl.scrollTop = logEl.scrollHeight; }
      function setBusy(el, busy) { el.disabled = !!busy; }

      function updateSnippets() {
        const origin = window.location.origin;
        const fileHint = sttFile.files && sttFile.files[0] ? sttFile.files[0].name : "audio.wav";
        const ttsExample = (ttsText.value || "Привет!").replaceAll("\\n", " ").slice(0, 120);
        const ttsEsc = ttsExample.replaceAll('\"', '\\\\\"');
        const mode = (ttsMode && ttsMode.value) ? ttsMode.value : "auto";
        snippetsEl.textContent =
`# health
curl -sS ${origin}/health

# STT
curl -sS -F "file=@${fileHint}" ${origin}/transcribe

# TTS (в ответе wav)
curl -sS -X POST ${origin}/api/tts \\
  -H "Content-Type: application/json" \\
  -d '{"text": "${ttsEsc}", "mode": "${mode}"}' > out.wav
`;
      }

      async function refreshHealth() {
        try {
          const r = await fetch("/health");
          const j = await r.json();
          healthDot.classList.remove("bad"); healthDot.classList.add("ok");
          healthText.textContent = "health: ok";
          deviceText.textContent = `device=${j.device}`;
        } catch (e) {
          healthDot.classList.remove("ok"); healthDot.classList.add("bad");
          healthText.textContent = "health: error";
          deviceText.textContent = "";
        }
      }

      btnTranscribeClear.addEventListener("click", () => {
        sttText.value = ""; sttSegments.textContent = ""; appendLog("STT output cleared");
      });
      btnTtsClear.addEventListener("click", () => {
        ttsText.value = ""; ttsAudio.removeAttribute("src"); ttsAudio.load(); appendLog("TTS cleared"); updateSnippets();
      });
      btnUseStt.addEventListener("click", () => {
        ttsText.value = sttText.value || ""; appendLog("Copied STT → TTS"); updateSnippets();
      });
      sttFile.addEventListener("change", updateSnippets);
      ttsText.addEventListener("input", updateSnippets);
      ttsMode && ttsMode.addEventListener("change", updateSnippets);

      btnTranscribe.addEventListener("click", async () => {
        if (!sttFile.files || !sttFile.files[0]) { appendLog("No file selected for STT"); return; }
        const f = sttFile.files[0];
        const fd = new FormData(); fd.append("file", f);
        setBusy(btnTranscribe, true);
        appendLog(`STT upload: ${f.name} (${f.type || "unknown"}, ${f.size} bytes)`);
        const t0 = performance.now();
        try {
          const r = await fetch("/transcribe", { method: "POST", body: fd });
          const t1 = performance.now();
          if (!r.ok) { const msg = await r.text(); appendLog(`STT error ${r.status}: ${msg}`); return; }
          const j = await r.json();
          const segs = Array.isArray(j.segments) ? j.segments : [];
          if (segs.length) {
            const grouped = [];
            let curSpk = null, curText = "";
            for (const s of segs) {
              const spk = s.speaker || "UNKNOWN";
              const txt = (s.text || "").trim();
              if (!txt) continue;
              if (curSpk === null) { curSpk = spk; curText = txt; }
              else if (spk === curSpk) { curText += " " + txt; }
              else { grouped.push(`[${curSpk}] ${curText}`); curSpk = spk; curText = txt; }
            }
            if (curSpk !== null) grouped.push(`[${curSpk}] ${curText}`);
            sttText.value = grouped.join("\\n");
            sttSegments.textContent = segs.map(s => `${s.speaker||"UNKNOWN"}\\t${Number(s.start||0).toFixed(2)}–${Number(s.end||0).toFixed(2)}\\t${(s.text||"").trim()}`).join("\\n");
          } else {
            sttText.value = j.text || "";
            sttSegments.textContent = "(no diarization segments)";
          }
          appendLog(`STT ok in ${(t1 - t0).toFixed(0)}ms`);
        } catch (e) {
          appendLog(`STT network error: ${e}`);
        } finally {
          setBusy(btnTranscribe, false);
        }
      });

      btnSpeak.addEventListener("click", async () => {
        const text = (ttsText.value || "").trim();
        if (!text) { appendLog("Empty text for TTS"); return; }
        const mode = (ttsMode && ttsMode.value) ? ttsMode.value : "auto";
        setBusy(btnSpeak, true);
        appendLog(`TTS request: ${text.length} chars`);
        const t0 = performance.now();
        try {
          const r = await fetch("/api/tts", { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ text, mode }) });
          const t1 = performance.now();
          if (!r.ok) { const msg = await r.text(); appendLog(`TTS error ${r.status}: ${msg}`); return; }
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          ttsAudio.src = url;
          await ttsAudio.play().catch(() => {});
          appendLog(`TTS ok in ${(t1 - t0).toFixed(0)}ms, ${blob.size} bytes`);
        } catch (e) {
          appendLog(`TTS network error: ${e}`);
        } finally {
          setBusy(btnSpeak, false);
        }
      });

      updateSnippets(); refreshHealth(); setInterval(refreshHealth, 4000);
    </script>
  </body>
</html>
    """.strip()

