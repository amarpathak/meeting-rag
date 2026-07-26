async function errorMessage(res) {
  const text = await res.text();
  try {
    return JSON.parse(text).detail || text;
  } catch {
    return text;
  }
}

async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

async function postJSON(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

async function upload(path, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(path, { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

export const api = {
  meetings: () => getJSON("/transcripts"),
  transcript: (id) => getJSON(`/transcripts/${id}`),
  ask: (question, transcriptId, refresh = false) =>
    postJSON("/ask", { question, transcript_id: transcriptId, refresh }),
  actions: (id, refresh = false) => getJSON(`/transcripts/${id}/actions${refresh ? "?refresh=true" : ""}`),
  ingestText: (file) => upload("/ingest", file),
  ingestAudio: (file) => upload("/transcribe?ingest=true", file),
  samples: () => getJSON("/samples"),
  ingestSample: (name) =>
    postJSON(name ? `/ingest-sample?name=${encodeURIComponent(name)}` : "/ingest-sample", {}),
  metrics: () => getJSON("/observability"),
  ingestYouTube: (url) => postJSON("/ingest-youtube", { url }),
};
