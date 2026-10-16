import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { readFileSync } from "node:fs";
// Only server addresses are consumed here; the configuration is never bundled.
const config = JSON.parse(
  readFileSync(new URL("../config.json", import.meta.url), "utf8").replace(
    /^\uFEFF/,
    "",
  ),
);
const apiHost = config.server.host.includes(":")
  ? `[${config.server.host}]`
  : config.server.host;
export default defineConfig({
  plugins: [vue()],
  server: {
    host: config.frontend.host,
    port: config.frontend.port,
    strictPort: true,
    fs: {
      deny: ["**/config.json", "**/.env*", "**/data-local/**", "**/*.sqlite3"],
    },
    proxy: {
      "/api": {
        target: `http://${apiHost}:${config.server.port}`,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: config.frontend.host,
    port: config.frontend.port,
    strictPort: true,
  },
  build: { outDir: "dist" },
});
