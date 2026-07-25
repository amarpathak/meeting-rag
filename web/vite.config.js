import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API paths to the FastAPI container so the browser talks to one origin
// (no CORS). Inside docker compose the backend is reachable as "api".
const backend = process.env.API_URL || "http://api:8000";
const apiPaths = ["/health", "/ingest", "/ingest-sample", "/ask", "/transcribe", "/transcripts"];

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: Object.fromEntries(apiPaths.map((p) => [p, backend])),
  },
});
