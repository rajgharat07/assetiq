import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/ask": "http://127.0.0.1:8000",
      "/users": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/ingest": "http://127.0.0.1:8000",
    },
  },
});
