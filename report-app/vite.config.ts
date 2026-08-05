import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../reports/ai-daily-2026-06-30",
    emptyOutDir: true,
  },
});
