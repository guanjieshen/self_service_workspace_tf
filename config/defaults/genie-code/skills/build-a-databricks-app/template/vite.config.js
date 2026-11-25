import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The page is built into dist/ at deploy (npm run build); the server serves it.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://localhost:8000" } },
});
