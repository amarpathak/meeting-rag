import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const SPK_HUES = [200, 158, 268, 24, 330, 96, 300];
function speakerHue(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return SPK_HUES[h % SPK_HUES.length];
}
const TS = /(\d{2}:\d{2}:\d{2})/g;

function AnswerText({ text, onCite }) {
  return (
    <p>
      {text.split(TS).map((part, i) =>
        /^\d{2}:\d{2}:\d{2}$/.test(part) ? (
          <button key={i} className="cite" onClick={() => onCite(part)}>{part}</button>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
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

function LoadModal({ onClose, onDone }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const run = async (label, fn) => {
    setBusy(label); setError("");
    try { await fn(); onDone(); } catch (e) { setError(e.message); } finally { setBusy(""); }
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Load a meeting</h3>
        <p className="muted">Add a transcript to interrogate. Audio is transcribed first.</p>

        <label className="drop">
          <b>Upload transcript (.txt)</b>
          <span>Speaker-labelled, [HH:MM:SS] format</span>
          <input type="file" accept=".txt,text/plain"
            onChange={(e) => e.target.files[0] && run("text", () => api.ingestText(e.target.files[0]))} />
        </label>

        <label className="drop">
          <b>Upload audio (.mp3 / .wav / .m4a …)</b>
          <span>Transcribed with Gemini, then ingested (~15–40s)</span>
          <input type="file" accept="audio/*,.aiff,.m4a"
            onChange={(e) => e.target.files[0] && run("audio", () => api.ingestAudio(e.target.files[0]))} />
        </label>

        <div className="row">
          <button className="btn" onClick={() => run("sample", api.ingestSample)}>
            {busy === "sample" ? <span className="spinner" /> : null} Load bundled sample
          </button>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
        {error ? (
          <p className="modal-err">{error}</p>
        ) : busy && busy !== "sample" ? (
          <p className="muted" style={{ marginTop: 12 }}><span className="spinner" /> Processing {busy}…</p>
        ) : null}
      </div>
    </div>
  );
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
    if (!currentId) { setTranscript(null); return; }
    setConversation([]); setActions(null); setTab("ask");
    api.transcript(currentId).then(setTranscript);
  }, [currentId]);

  const gotoTs = (ts) => {
    const el = turnRefs.current[ts];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlashTs(ts);
    setTimeout(() => setFlashTs((v) => (v === ts ? null : v)), 1600);
  };

  const ask = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || !currentId || asking) return;
    const id = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
    setConversation((c) => [...c, { id, question: q, data: null, error: null }]);
    setQuestion("");
    setAsking(true);
    try {
      const data = await api.ask(q, currentId);
      setConversation((c) => c.map((x) => (x.id === id ? { ...x, data } : x)));
    } catch (err) {
      setConversation((c) => c.map((x) => (x.id === id ? { ...x, error: String(err) } : x)));
    } finally {
      setAsking(false);
    }
  };

  const loadActions = async () => {
    if (!currentId) return;
    setActionsLoading(true);
    try { setActions((await api.actions(currentId)).action_items); }
    finally { setActionsLoading(false); }
  };

  const meetingName = (m) => m.title || m.filename || `Meeting ${m.id}`;

  return (
    <div className="app">
      <header className="header">
        <div className="brand"><b>Meeting Intelligence</b><span>grounded Q&amp;A · citations · actions</span></div>
        <div className="spacer" />
        {meetings.length > 0 && (
          <select className="select" value={currentId ?? ""} onChange={(e) => setCurrentId(Number(e.target.value))}>
            {meetings.map((m) => <option key={m.id} value={m.id}>{meetingName(m)}</option>)}
          </select>
        )}
        <button className="btn primary" onClick={() => setShowLoad(true)}>＋ Load meeting</button>
        <button className="btn ghost" title="Toggle theme"
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}>◐</button>
      </header>

      {meetings.length === 0 ? (
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
                <div className="pane-body">
                  {conversation.length === 0 ? (
                    <p className="muted">Ask anything grounded in this meeting — off-topic questions are refused. Try “What was the hazard ratio?” or “When is the ESC abstract due?”</p>
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
                              <div className="status">{x.data.answered ? "answered" : "refused"}</div>
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
                  <button className="btn" onClick={loadActions} disabled={actionsLoading}>
                    {actionsLoading ? <span className="spinner" /> : "↻"} Re-extract
                  </button>
                </div>
                <div className="pane-body">
                  {actionsLoading && actions === null ? (
                    <p className="muted"><span className="spinner" /> Extracting commitments…</p>
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

      {showLoad && (
        <LoadModal onClose={() => setShowLoad(false)}
          onDone={async () => { setShowLoad(false); const before = new Set(meetings.map((m) => m.id));
            const list = await api.meetings(); setMeetings(list);
            const fresh = list.find((m) => !before.has(m.id)); setCurrentId((fresh ?? list[list.length - 1])?.id ?? null); }} />
      )}
    </div>
  );
}
