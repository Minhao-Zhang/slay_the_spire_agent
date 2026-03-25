import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** Backend URL for the Python `control_api` (FastAPI / uvicorn). */
const API_ORIGIN = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: API_ORIGIN,
        changeOrigin: true,
      },
      "/ws": {
        target: API_ORIGIN,
        ws: true,
      },
    },
  },
});
