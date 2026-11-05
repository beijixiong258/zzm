import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
  plugins: [vue()],
  optimizeDeps: { entries: ["index.html"] },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8001" },
    },
    fs: {
      deny: [
        "**/application.yaml",
        "**/config.json",
        "**/.env*",
        "**/data-local/**",
        "**/*.sqlite3",
      ],
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
  build: { outDir: "dist" },
});
