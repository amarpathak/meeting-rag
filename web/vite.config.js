import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API paths to the FastAPI container so the browser talks to one origin
// (no CORS). Inside docker compose the backend is reachable as "api".
const backend = process.env.API_URL || "http://api:8000";
// A path missing here is not a 404 — the SPA's index.html is served with a 200,
// so the fetch fails on JSON parsing instead. Add every backend route.
const apiPaths = ["/health", "/ingest", "/ingest-sample", "/ingest-youtube", "/ask", "/transcribe",
  "/transcripts", "/samples", "/observability"];

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: Object.fromEntries(apiPaths.map((p) => [p, backend])),
  },
});
