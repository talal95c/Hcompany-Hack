import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    allowedHosts: [".preview.devinapps.com"],
  },
  preview: { allowedHosts: [".preview.devinapps.com"] },
  test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"], css: false },
});
