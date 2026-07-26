import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const SPK_HUES = [200, 158, 268, 24, 330, 96, 300];
function speakerHue(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return SPK_HUES[h % SPK_HUES.length];
}
// Bold, inline code and timestamps, in one pass so a citation inside a bold run
// still renders as a clickable button.
const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\d{1,2}:\d{2}:\d{2})/g;
const BULLET = /^(?:[*\-•]|\d+[.)])\s+(.*)$/;

function Inline({ text, onCite }) {
  return text.split(INLINE).map((part, i) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (/^`[^`]+`$/.test(part)) return <code key={i}>{part.slice(1, -1)}</code>;
    if (/^\d{1,2}:\d{2}:\d{2}$/.test(part))
      return <button key={i} className="cite" onClick={() => onCite(part)}>{part}</button>;
    return <span key={i}>{part}</span>;
  });
}

// The model answers in markdown. Rendering it into a single <p> collapsed the
// newlines, so bullets ran together and the asterisks showed up as literal text.
function AnswerText({ text, onCite }) {
  const blocks = [];
  let para = [];
  let list = [];
  const flushPara = () => { if (para.length) { blocks.push({ kind: "p", lines: para }); para = []; } };
  const flushList = () => { if (list.length) { blocks.push({ kind: "ul", items: list }); list = []; } };

  for (const raw of (text || "").split("\n")) {
    const line = raw.trim();
    if (!line) { flushPara(); flushList(); continue; }
    const bullet = line.match(BULLET);
    if (bullet) { flushPara(); list.push(bullet[1]); }
    else { flushList(); para.push(line); }
  }
  flushPara();
  flushList();

  return (
    <div className="answer">
      {blocks.map((b, i) =>
        b.kind === "ul" ? (
          <ul key={i}>
            {b.items.map((item, j) => <li key={j}><Inline text={item} onCite={onCite} /></li>)}
          </ul>
        ) : (
          <p key={i}><Inline text={b.lines.join(" ")} onCite={onCite} /></p>
        ),
      )}
    </div>
  );
}

function Score({ value }) {
  const floor = 0.6;
  return (
    <div className="score">
      <span className="lbl">match</span>
      <div className="meter">
        <div className="fill" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
        <div className="floor" style={{ left: `${floor * 100}%` }} title="refusal floor 0.60" />
      </div>
      <span className="val">{value.toFixed(2)}</span>
    </div>
  );
}

// Deliberately meeting-agnostic: the previous placeholder suggested "What was the
// hazard ratio?" on every meeting, which is nonsense on all but one of them.
// These map to what someone actually wants from a transcript they didn't attend.
const STARTERS = [
  { icon: "≡", label: "Summarise this meeting", q: "Summarise this meeting in a few key points." },
  { icon: "✓", label: "Decisions made", q: "What decisions were made, and who made them?" },
  { icon: "→", label: "Action items & owners", q: "What are the action items and who owns each one?" },
  { icon: "◷", label: "Deadlines", q: "What deadlines or dates were committed to?" },
  { icon: "?", label: "Open questions", q: "What was left unresolved or still open at the end?" },
  { icon: "⚡", label: "Disagreements", q: "Where did people disagree, and what were the concerns raised?" },
];

const BUSY_NOTE = {
  text: "Chunking and embedding…",
  audio: "Transcribing the audio with Gemini, then ingesting…",
  youtube: "Fetching captions, inferring speakers, then ingesting… (up to ~90s)",
};
const busyNote = (b) => (b.startsWith("sample:") ? "Chunking and embedding…" : BUSY_NOTE[b]);

// Verified to have captions and to ingest cleanly. Clicking fills the field
// instead of fetching, because the fetch itself spends a model call and that
// should stay a deliberate press of the button.
const YOUTUBE_EXAMPLES = [
  { label: "GitLab engineering (public)", url: "https://www.youtube.com/watch?v=qGFoZ8yodc4" },
  { label: "GitLab product marketing", url: "https://www.youtube.com/watch?v=lBVtvOpU80Q" },
];

function LoadModal({ onClose, onDone, onPick }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");
  const [samples, setSamples] = useState(null);

  // Fetched on open rather than held in App state: whether a sample is already
  // loaded changes as you load them, and a stale "load" button on a meeting that
  // is already in the library is a click that silently does nothing.
  const loadSamples = () => api.samples().then(setSamples).catch(() => setSamples([]));
  useEffect(() => { loadSamples(); }, []);

  const run = async (label, fn) => {
    setBusy(label); setError("");
    try { await fn(); onDone(); } catch (e) { setError(e.message); } finally { setBusy(""); }
  };

  // Escape is the reflex for dismissing a dialog; without it the only way out
  // was a click on the backdrop, which isn't discoverable.
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const submitUrl = (e) => {
    e.preventDefault();
    if (url.trim() && !busy) run("youtube", () => api.ingestYouTube(url.trim()));
  };

  return (
    <div className="overlay" onClick={() => !busy && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Load a meeting"
        onClick={(e) => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose} disabled={!!busy} aria-label="Close">×</button>

        <h3>Load a meeting</h3>
        <p className="muted">Anything with speakers and timing. The bundled transcripts are already
          in the expected format; everything else may need a model call first.</p>

        <div className="modal-sec first">
          <h4>Bundled transcripts</h4>
          <span className="tag free">no model call</span>
        </div>

        {samples === null ? (
          <p className="muted"><span className="spinner" /> Reading the data folder…</p>
        ) : samples.length === 0 ? (
          <p className="muted">No transcripts found in <code>data/transcripts</code>.</p>
        ) : (
          <div className="samples">
            {samples.map((s) => {
              const loading = busy === `sample:${s.name}`;
              // Already in the library: ingest would be a no-op, so the row opens
              // the meeting instead of being a button that does nothing.
              const loaded = s.transcript_id !== null;
              return (
                <button key={s.name} className={"sample" + (loaded ? " loaded" : "")} disabled={!!busy}
                  onClick={() => (loaded
                    ? onPick(s.transcript_id)
                    : run(`sample:${s.name}`, () => api.ingestSample(s.name)))}>
                  <span className="sample-text">
                    <b>{s.title}</b>
                    <em>{s.turns} turns · {s.speakers} speakers{s.date ? ` · ${s.date}` : ""}</em>
                  </span>
                  <span className="sample-act">
                    {loading ? <span className="spinner" /> : loaded ? "open →" : "load →"}
                  </span>
                </button>
              );
            })}
          </div>
        )}
        <p className="hint">Parsed straight from <code>data/transcripts</code> — chunked and embedded,
          with nothing sent to a generative model.</p>

        <div className="modal-sec">
          <h4>From a YouTube link</h4>
          <span className="tag cost">1 model call</span>
        </div>
        <form className="urlrow" onSubmit={submitUrl}>
          <div className="urlfield">
            <span className="urlicon" aria-hidden="true">▶</span>
            <input type="url" value={url} placeholder="Paste a YouTube link…"
              onChange={(e) => setUrl(e.target.value)} disabled={!!busy} />
          </div>
          <button className="btn primary" disabled={!url.trim() || !!busy}>
            {busy === "youtube" ? <span className="spinner" /> : null} Fetch
          </button>
        </form>
        <p className="hint">The captions themselves are free — the model call infers where the speaker
          turns are, so names read as Speaker 1, 2, 3.</p>
        <div className="examples">
          <span className="examples-lbl">try</span>
          {YOUTUBE_EXAMPLES.map((ex) => (
            <button key={ex.url} type="button" className="example-chip" disabled={!!busy}
              title={ex.url} onClick={() => setUrl(ex.url)}>{ex.label}</button>
          ))}
        </div>

        <div className="modal-sec">
          <h4>From a file</h4>
          <span className="tag cost">may cost 1 model call</span>
        </div>
        <div className="drops">
          <label className="drop">
            <b>Transcript</b>
            <span>.txt with speakers and timestamps</span>
            <span className="cost-note">free if it parses · 1 call to normalise if not</span>
            <input type="file" accept=".txt,text/plain" disabled={!!busy}
              onChange={(e) => e.target.files[0] && run("text", () => api.ingestText(e.target.files[0]))} />
          </label>
          <label className="drop">
            <b>Audio</b>
            <span>.mp3 · .wav · .m4a</span>
            <span className="cost-note">1 transcription call · try data/audio/</span>
            <input type="file" accept="audio/*,.aiff,.m4a" disabled={!!busy}
              onChange={(e) => e.target.files[0] && run("audio", () => api.ingestAudio(e.target.files[0]))} />
          </label>
        </div>

        {error ? <p className="modal-err">{error}</p> : null}
        {busy ? <p className="modal-busy"><span className="spinner" /> {busyNote(busy)}</p> : null}
      </div>
    </div>
  );
}

const money = (n) => (n >= 1 ? `$${n.toFixed(2)}` : `${(n * 100).toFixed(3)}¢`);
const ms = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${n}ms`);
const tokens = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

const ROUTE_NOTE = {
  answered: "question answered from retrieved chunks",
  refused_low_similarity: "refused below the similarity floor — no model call",
  extract_actions: "action item extraction",
  normalize: "reformatting a non-standard upload",
  transcribe: "audio → transcript",
};

function Telemetry({ data, loading, error, onRefresh }) {
  if (error) return <div className="pane-body"><div className="a refused">
    <div className="status">error</div><p>{error}</p></div></div>;
  if (!data) return <div className="pane-body"><p className="muted">
    <span className="spinner" /> Loading metrics…</p></div>;

  const { totals, guardrail, by_route, by_model, by_meeting, unattributed, recent,
    failures } = data;
  // A refusal is the guardrail working, not a failure, so it is framed as
  // coverage rather than an error rate.
  const refusalPct = (guardrail.refusal_rate * 100).toFixed(0);

  return (
    <>
      <div className="actions-top">
        <button className="btn" onClick={onRefresh} disabled={loading}
          title="Re-read query_log">
          {loading ? <span className="spinner" /> : "↻"} Refresh
        </button>
        <span className="extract-meta">every model call is recorded in <code>query_log</code></span>
      </div>
      <div className="pane-body">
        <div className="stats">
          <div className="stat"><span className="k">model calls</span><b>{totals.calls}</b></div>
          <div className="stat"><span className="k">total cost</span><b>{money(totals.cost_usd)}</b></div>
          <div className="stat"><span className="k">avg latency</span><b>{ms(totals.avg_latency_ms)}</b></div>
          <div className="stat"><span className="k">tokens in / out</span>
            <b>{tokens(totals.input_tokens)} / {tokens(totals.output_tokens)}</b></div>
          <div className={"stat" + (totals.failed ? " bad" : "")}
            title="Calls the provider rejected or that never reached it — quota, auth, network">
            <span className="k">failed calls</span><b>{totals.failed}</b></div>
        </div>

        {failures.length > 0 && (
          <>
            <h3 className="sec">Failures</h3>
            <div className="stack-alerts">
              {failures.map((f, i) => (
                <div className="alert" key={i}>
                  <div className="alert-head">
                    <span className="alert-route">{f.route}</span>
                    {f.count > 1 && <span className="chip">×{f.count}</span>}
                    <span className="alert-when">{new Date(f.last_seen).toLocaleTimeString()}</span>
                  </div>
                  <p>{f.error}</p>
                </div>
              ))}
            </div>
          </>
        )}

        <h3 className="sec">Guardrail</h3>
        <div className="stats">
          <div className="stat"><span className="k">questions asked</span><b>{guardrail.questions}</b></div>
          <div className="stat" title="Below the similarity floor, so answered without calling the model">
            <span className="k">refused</span><b>{guardrail.refused} <em>({refusalPct}%)</em></b></div>
          <div className="stat"><span className="k">avg top score</span>
            <b>{guardrail.avg_top_score_when_answered}</b></div>
        </div>

        <h3 className="sec">By route</h3>
        <div className="tablewrap">
          <table className="tbl">
            <thead><tr><th>route</th><th>calls</th><th>failed</th><th>avg</th><th>p95</th>
              <th>tokens</th><th>cost</th></tr></thead>
            <tbody>
              {by_route.map((r) => (
                <tr key={r.route}>
                  <td title={ROUTE_NOTE[r.route] || ""}>{r.route}</td>
                  <td>{r.calls}</td>
                  <td className={r.failed ? "cell-bad" : ""}>{r.failed || "—"}</td>
                  <td>{ms(r.avg_latency_ms)}</td><td>{ms(r.p95_latency_ms)}</td>
                  <td>{tokens(r.input_tokens + r.output_tokens)}</td>
                  <td>{money(r.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {by_model.length > 0 && (
          <>
            <h3 className="sec">By model <em className="sec-note">fallback chain, best first</em></h3>
            <div className="tablewrap">
              <table className="tbl">
                <thead><tr><th>model</th><th>calls</th><th>served</th><th>failed</th><th>cost</th></tr></thead>
                <tbody>
                  {by_model.map((m) => (
                    <tr key={m.model}>
                      <td>{m.model}</td><td>{m.calls}</td><td>{m.ok}</td>
                      <td className={m.failed ? "cell-bad" : ""}>{m.failed || "—"}</td>
                      <td>{money(m.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        <h3 className="sec">Cost by meeting</h3>
        <div className="tablewrap">
          <table className="tbl">
            <thead><tr><th>meeting</th><th>calls</th><th>asked</th><th>refused</th>
              <th>extractions</th><th>tokens</th><th>cost</th></tr></thead>
            <tbody>
              {by_meeting.map((m) => (
                <tr key={m.transcript_id}>
                  <td className="q-cell" title={m.name}>{m.name}</td>
                  <td>{m.calls}</td><td>{m.answered}</td><td>{m.refused}</td>
                  <td>{m.extractions}</td><td>{tokens(m.tokens)}</td><td>{money(m.cost_usd)}</td>
                </tr>
              ))}
              {unattributed.calls > 0 && (
                <tr className="row-muted"
                  title="Audio transcription and upload normalisation run before a transcript row exists, so they belong to no meeting">
                  <td>unattributed</td>
                  <td>{unattributed.calls}</td><td>—</td><td>—</td><td>—</td><td>—</td>
                  <td>{money(unattributed.cost_usd)}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <h3 className="sec">Recent calls</h3>
        <div className="tablewrap">
          <table className="tbl">
            <thead><tr><th>when</th><th>route</th><th>detail</th><th>score</th><th>latency</th><th>cost</th></tr></thead>
            <tbody>
              {recent.map((r, i) => (
                <tr key={i} className={r.error ? "row-failed" : r.answered ? "" : "row-refused"}>
                  <td>{new Date(r.created_at).toLocaleTimeString()}</td>
                  <td>{r.error ? `${r.route} · failed` : r.route}</td>
                  <td className="q-cell" title={r.error || r.question}>{r.error || r.question}</td>
                  <td>{r.top_score === null ? "—" : r.top_score.toFixed(3)}</td>
                  <td>{ms(r.latency_ms)}</td>
                  <td>{money(r.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function relativeAge(iso, now) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((now - then) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export default function App() {
  const [meetings, setMeetings] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [conversation, setConversation] = useState([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [tab, setTab] = useState("ask");
  const [actions, setActions] = useState(null);
  const [actionsError, setActionsError] = useState("");
  const [actionsCached, setActionsCached] = useState(false);
  const [actionsAt, setActionsAt] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsError, setMetricsError] = useState("");
  const [view, setView] = useState("meeting");
  // Keyed by meeting: a question asked of one transcript is meaningless against
  // another, and clicking it would just spend a call to get a refusal.
  const [recentByMeeting, setRecentByMeeting] = useState(() => {
    try { return JSON.parse(localStorage.getItem("recentQuestions.v2") || "{}"); } catch { return {}; }
  });
  const recent = (currentId && recentByMeeting[currentId]) || [];
  const [now, setNow] = useState(() => Date.now());
  const [actionsLoading, setActionsLoading] = useState(false);
  const [flashTs, setFlashTs] = useState(null);
  const [showLoad, setShowLoad] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "auto");
  const turnRefs = useRef({});

  useEffect(() => {
    if (theme === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const refreshMeetings = async (selectId) => {
    const list = await api.meetings();
    setMeetings(list);
    const pick = selectId ?? (list.some((m) => m.id === currentId) ? currentId : list[0]?.id ?? null);
    setCurrentId(pick);
  };

  useEffect(() => { refreshMeetings(); }, []);

  useEffect(() => {
    localStorage.setItem("recentQuestions.v2", JSON.stringify(recentByMeeting));
  }, [recentByMeeting]);

  // Escape closes the dashboard, matching the load dialog. The modal has its own
  // handler and takes priority, so this only fires when no dialog is open.
  useEffect(() => {
    if (view !== "observability") return;
    const onKey = (e) => { if (e.key === "Escape" && !showLoad) closeMetrics(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, showLoad]);

  // Without a tick the label freezes at render, so a cached result keeps claiming
  // it was extracted "just now" long after it was.
  useEffect(() => {
    if (!actionsAt) return;
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, [actionsAt]);

  useEffect(() => {
    if (!currentId) { setTranscript(null); return; }
    setConversation([]); setActions(null); setActionsError(""); setActionsCached(false);
    setActionsAt(null); setTab("ask");
    api.transcript(currentId).then(setTranscript);
  }, [currentId]);

  const gotoTs = (ts) => {
    const el = turnRefs.current[ts];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    // Clearing first restarts the pulse when the same citation is clicked twice:
    // setting state to the value it already holds would not re-render.
    setFlashTs(null);
    requestAnimationFrame(() => setFlashTs(ts));
    setTimeout(() => setFlashTs((v) => (v === ts ? null : v)), 1100);
  };

  const ask = async (e, preset, refresh = false) => {
    e?.preventDefault();
    const q = (preset ?? question).trim();
    if (!q || !currentId || asking) return;
    // Survives meeting switches and reloads — switching clears the conversation,
    // and re-typing a question you just asked is pure friction.
    setRecentByMeeting((all) => ({
      ...all,
      [currentId]: [q, ...(all[currentId] || []).filter((x) => x !== q)].slice(0, 8),
    }));
    const id = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
    setConversation((c) => [...c, { id, question: q, data: null, error: null }]);
    setQuestion("");
    setAsking(true);
    try {
      const data = await api.ask(q, currentId, refresh);
      setConversation((c) => c.map((x) => (x.id === id ? { ...x, data } : x)));
    } catch (err) {
      setConversation((c) => c.map((x) => (x.id === id ? { ...x, error: String(err) } : x)));
    } finally {
      setAsking(false);
    }
  };

  const loadActions = async (refresh = false) => {
    if (!currentId) return;
    setActionsLoading(true);
    setActionsError("");
    // Without this catch a failed extraction leaves actions null, which the pane
    // renders as "No action items found" — a failure that reads as a result.
    try {
      const res = await api.actions(currentId, refresh);
      setActions(res.action_items);
      setActionsCached(res.cached);
      setActionsAt(res.extracted_at);
      setNow(Date.now());
    }
    catch (err) { setActionsError(err.message || String(err)); }
    finally { setActionsLoading(false); }
  };

  // Always refetched on open rather than cached: a dashboard that can show a
  // stale call count is worse than one that takes 20ms to load.
  const loadMetrics = async () => {
    setMetricsLoading(true);
    setMetricsError("");
    try { setMetrics(await api.metrics()); }
    catch (err) { setMetricsError(err.message || String(err)); }
    finally { setMetricsLoading(false); }
  };

  const openMetrics = () => { setView("observability"); loadMetrics(); };
  const closeMetrics = () => setView("meeting");

  const meetingName = (m) => m.title || m.filename || `Meeting ${m.id}`;

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <span className="mark" aria-hidden="true">◍</span>
          <span className="brand-text">
            <b>Meeting Intelligence</b>
            <span className="sub">grounded Q&amp;A</span>
          </span>
        </div>

        <button className="btn primary load-btn" onClick={() => setShowLoad(true)}>
          ＋ Load meeting
        </button>

        <div className="side-sec">
          <span className="side-lbl">Meetings</span>
          {meetings.length > 0 && <span className="side-count">{meetings.length}</span>}
        </div>

        <nav className="side-list" aria-label="Meetings">
          {meetings.length === 0 ? (
            <p className="side-empty">Nothing loaded yet.</p>
          ) : meetings.map((m) => (
            <button key={m.id} title={meetingName(m)}
              className={"side-item" + (m.id === currentId && view === "meeting" ? " on" : "")}
              onClick={() => { setCurrentId(m.id); setView("meeting"); }}>
              <span className="side-item-name">{meetingName(m)}</span>
              <span className="side-item-meta">{m.chunks} chunks</span>
            </button>
          ))}
        </nav>

        <div className="side-foot">
          <button className={"side-nav" + (view === "observability" ? " on" : "")}
            title="Model call metrics across every meeting"
            onClick={() => (view === "observability" ? closeMetrics() : openMetrics())}>
            <span className="side-nav-icon" aria-hidden="true">◍</span> Observability
          </button>
          <button className="side-nav" title="Toggle theme"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}>
            <span className="side-nav-icon" aria-hidden="true">◐</span>
            {theme === "dark" ? "Light theme" : "Dark theme"}
          </button>
        </div>
      </aside>

      <main className="main">
      {view === "observability" ? (
        // Deliberately outside the meeting workspace: these metrics span every
        // meeting, so scoping them to the selected one would misrepresent them.
        <div className="work solo">
          <section className="pane">
            <div className="pane-head">
              <h2>Observability</h2>
              <span className="count">all meetings</span>
              <button className="pane-x" onClick={closeMetrics} title="Close (Esc)"
                aria-label="Close observability">×</button>
            </div>
            <Telemetry data={metrics} loading={metricsLoading} error={metricsError}
              onRefresh={loadMetrics} />
          </section>
        </div>
      ) : meetings.length === 0 ? (
        <div className="empty">
          <h3>No meetings yet</h3>
          <p className="muted">Load the bundled sample or upload a transcript to begin.</p>
          <button className="btn primary" onClick={() => setShowLoad(true)}>Load a meeting</button>
        </div>
      ) : (
        <div className="work">
          <section className="pane left">
            <div className="pane-head">
              <h2>{transcript?.title || meetings.find((m) => m.id === currentId)?.filename || "Transcript"}</h2>
              <span className="count">{transcript?.turns.length ?? 0} turns</span>
            </div>
            <div className="pane-body">
              {transcript?.turns.map((t, i) => {
                const hue = speakerHue(t.speaker);
                return (
                  <div key={i} ref={(el) => (turnRefs.current[t.timestamp] = el)}
                    className={"turn" + (flashTs === t.timestamp ? " flash" : "")}>
                    <div className="turn-meta">
                      <span className="ts">{t.timestamp}</span>
                      <span className="spk" style={{ color: `hsl(${hue} 48% 45%)` }}>
                        <span className="dot" style={{ background: `hsl(${hue} 48% 50%)` }} />{t.speaker}
                      </span>
                    </div>
                    <p className="turn-text">{t.text}</p>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="pane">
            <div className="tabs">
              <button className={"tab" + (tab === "ask" ? " on" : "")} onClick={() => setTab("ask")}>Ask</button>
              <button className={"tab" + (tab === "actions" ? " on" : "")}
                onClick={() => { setTab("actions"); if (actions === null && !actionsLoading) loadActions(); }}>
                Action items
              </button>
            </div>

            {tab === "ask" ? (
              <>
                <form className="askform" onSubmit={ask}>
                  <input value={question} onChange={(e) => setQuestion(e.target.value)}
                    placeholder="Ask about this meeting…" />
                  <button className="btn primary" disabled={asking}>{asking ? <span className="spinner" /> : "Ask"}</button>
                </form>
                {recent.length > 0 && (
                  <div className="recents">
                    <span className="recents-lbl">recent</span>
                    <div className="recents-list">
                      {recent.map((q) => (
                        <button key={q} className="recent-chip" title={q} disabled={asking}
                          onClick={() => ask(null, q)}>{q}</button>
                      ))}
                    </div>
                    <button className="recents-clear" title="Clear this meeting's recent questions"
                      onClick={() => setRecentByMeeting((all) => ({ ...all, [currentId]: [] }))}>
                      clear
                    </button>
                  </div>
                )}
                <div className="pane-body">
                  {conversation.length === 0 ? (
                    <div className="starters">
                      <p className="muted">Every answer is grounded in this transcript and cites the
                        moment it came from. Questions the meeting never covered are refused.</p>
                      <div className="starter-grid">
                        {STARTERS.map((s) => (
                          <button key={s.label} className="starter" disabled={asking}
                            onClick={() => ask(null, s.q)}>
                            <span className="starter-icon" aria-hidden="true">{s.icon}</span>
                            <span className="starter-text">
                              <b>{s.label}</b>
                              <em>{s.q}</em>
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="qa">
                      {conversation.map((x) => (
                        <div className="exchange" key={x.id}>
                          <div className="q">{x.question}</div>
                          {x.error ? (
                            <div className="a refused"><div className="status">error</div><p>{x.error}</p></div>
                          ) : !x.data ? (
                            <div className="a"><div className="status"><span className="spinner" /> thinking</div></div>
                          ) : (
                            <div className={"a" + (x.data.answered ? "" : " refused")}>
                              <div className="status">
                                {x.data.answered ? "answered" : "refused"}
                                {x.data.cached && (
                                  <>
                                    <span className="chip" title={"First answered " +
                                      new Date(x.data.answered_at).toLocaleString() +
                                      " — served from cache, no model call"}>cached</span>
                                    <button className="reask" disabled={asking}
                                      title="Discard the cached answer and ask the model again"
                                      onClick={() => ask(null, x.question, true)}>ask again</button>
                                  </>
                                )}
                              </div>
                              <AnswerText text={x.data.answer} onCite={gotoTs} />
                              <Score value={x.data.top_score} />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <>
                <div className="actions-top">
                  <button className="btn" onClick={() => loadActions(true)} disabled={actionsLoading}
                    title="Discard the cached result and run a fresh extraction (uses a model call)">
                    {actionsLoading ? <span className="spinner" /> : "↻"} Re-extract
                  </button>
                  {actionsAt && !actionsLoading && !actionsError && (
                    <span className="extract-meta" title={new Date(actionsAt).toLocaleString()}>
                      {actionsCached && <span className="chip">cached</span>}
                      extracted {relativeAge(actionsAt, now)}
                    </span>
                  )}
                </div>
                <div className="pane-body">
                  {actionsLoading && actions === null ? (
                    <p className="muted"><span className="spinner" /> Extracting commitments…</p>
                  ) : actionsError ? (
                    <div className="a refused"><div className="status">error</div><p>{actionsError}</p></div>
                  ) : actions && actions.length ? (
                    <div className="acts">
                      {actions.map((a, i) => (
                        <div className="act" key={i}>
                          <div className="owner">{a.owner}</div>
                          <div className="task">{a.task}</div>
                          <div className="meta">
                            {a.due ? <span className="chip due">due {a.due}</span> : <span className="chip">no deadline</span>}
                            <button className="chip ts" title="jump to this moment"
                              onClick={() => gotoTs(a.timestamp)}>{a.timestamp}</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="muted">No action items found.</p>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      )}
      </main>

      {showLoad && (
        <LoadModal onClose={() => setShowLoad(false)}
          onPick={(id) => { setShowLoad(false); setView("meeting"); setCurrentId(id); }}
          onDone={async () => { setShowLoad(false); setView("meeting");
            const before = new Set(meetings.map((m) => m.id));
            const list = await api.meetings(); setMeetings(list);
            const fresh = list.find((m) => !before.has(m.id)); setCurrentId((fresh ?? list[list.length - 1])?.id ?? null); }} />
      )}
    </div>
  );
}
