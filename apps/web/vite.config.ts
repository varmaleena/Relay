import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
export default defineConfig({
  root: resolve(import.meta.dirname),
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    fs: {
      allow: [
        resolve(import.meta.dirname),
        resolve(import.meta.dirname, "../../node_modules"),
      ],
    },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
});
