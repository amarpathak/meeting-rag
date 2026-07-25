async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function postJSON(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function upload(path, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(path, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  meetings: () => getJSON("/transcripts"),
  transcript: (id) => getJSON(`/transcripts/${id}`),
  ask: (question, transcriptId) => postJSON("/ask", { question, transcript_id: transcriptId }),
  actions: (id) => getJSON(`/transcripts/${id}/actions`),
  ingestText: (file) => upload("/ingest", file),
  ingestAudio: (file) => upload("/transcribe?ingest=true", file),
  ingestSample: () => postJSON("/ingest-sample", {}),
};
