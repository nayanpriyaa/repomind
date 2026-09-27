import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend calls /api/*; the dev server forwards to FastAPI on :8000 with the prefix stripped.
// Set VITE_API_BASE_URL (e.g. http://localhost:8000) to bypass the proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
