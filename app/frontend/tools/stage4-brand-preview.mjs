import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "../..");
const out = path.join(root, "artifacts/stage4/brand");
await fs.mkdir(out, { recursive: true });
const read = (name) =>
  fs.readFile(path.join(root, "frontend/public", name), "utf8");
const [full, white, small] = await Promise.all([
  read("aicademiya-mark.svg"),
  read("aicademiya-mark-light.svg"),
  read("aicademiya-mark-small.svg"),
]);
const ref = (
  await fs.readFile(
    path.join(root, "artifacts/stage4/references/logo-reference.png"),
  )
).toString("base64");
const html = `<!doctype html><meta charset="utf-8"><title>AIcademiya · Brand preview</title><style>
*{box-sizing:border-box}body{margin:0;background:#eeeee7;color:#285f50;font-family:Arial,sans-serif;padding:40px}h1{font:32px Georgia;margin:0 0 8px}p{margin:0 0 28px;color:#67766b;font-size:14px}.board{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}.tile{padding:25px;background:#faf9f2;border-radius:14px;text-align:center;min-width:0}.tile svg,.tile img{width:250px;height:270px;object-fit:contain;display:block;margin:auto}.tile.dark{background:#285f50;color:#f7f6ed}.tile.ref{background:#1c2229;color:#c8d6be}.tile small{display:block;margin-top:14px}.wordmark{font:26px Georgia;display:block;margin-top:14px}.strip{display:flex;align-items:end;justify-content:space-around;background:#faf9f2;border-radius:14px;padding:25px;margin-top:20px;gap:24px}.strip div{text-align:center}.strip svg{display:block;margin:auto}.strip small{display:block;margin-top:12px;color:#61776b;font-size:12px}footer{margin-top:22px;font-size:13px;color:#61766c}
</style><h1>AIcademiya</h1><p>Reference silhouette, open-book foundation. Optical simplification for smaller sizes.</p><div class="board"><div class="tile ref"><img src="data:image/png;base64,${ref}"><small>Provided reference</small></div><div class="tile">${full}<span class="wordmark">AIcademiya</span><small>Detailed mark · green on light</small></div><div class="tile dark">${white}<span class="wordmark">AIcademiya</span><small>Detailed mark · light on green</small></div></div><div class="strip">${[16, 32, 48, 72, 96].map((n) => `<div>${small.replace("<svg ", `<svg width="${n}" height="${n}" `)}<small>${n}px · small mark</small></div>`).join("")}</div><footer>The small mark keeps the portrait, paired arch, side flourishes and open book with fewer interior strokes.</footer>`;
await fs.writeFile(path.join(out, "preview.html"), html);
if (process.env.TMPDIR) {
  process.env.TEMP = process.env.TMPDIR;
  process.env.TMP = process.env.TMPDIR;
}
const browser = await chromium.launch({
  headless: true,
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
});
try {
  const page = await browser.newPage({
    viewport: { width: 1140, height: 850 },
    deviceScaleFactor: 1,
  });
  await page.setContent(html);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: path.join(out, "preview.png"),
    fullPage: true,
  });
  console.log(
    JSON.stringify({
      html: path.join(out, "preview.html"),
      screenshot: path.join(out, "preview.png"),
      svg_count: await page.locator("svg").count(),
    }),
  );
} finally {
  await browser.close();
}
