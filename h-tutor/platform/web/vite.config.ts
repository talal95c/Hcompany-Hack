import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The console is served by the Worker as static assets (wrangler.toml [assets]).
export default defineConfig({
  root: __dirname,
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
  // App icons are shared with the Rio app (../../src/assets/apps).
  server: { fs: { allow: ["..", "../.."] } },
});
