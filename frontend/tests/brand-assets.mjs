// Render original SVG favicon locally; no external assets or network.
import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "..");
const svg = await fs.readFile(path.join(root, "public/favicon.svg"), "utf8");
if (process.env.TMPDIR) {
  process.env.TEMP = process.env.TMPDIR;
  process.env.TMP = process.env.TMPDIR;
}
const browser = await chromium.launch({
  headless: true,
  executablePath:
    process.env.CHROME_PATH ||
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
});
try {
  const page = await browser.newPage();
  const images = [];
  for (const size of [32, 48, 180]) {
    await page.setViewportSize({ width: size, height: size });
    await page.setContent(
      `<style>html,body{margin:0}svg{width:${size}px;height:${size}px;display:block}</style>${svg}`,
    );
    const file = size === 180 ? "apple-touch-icon.png" : `favicon-${size}.png`;
    const bytes = await page.screenshot({
      path: path.join(root, "public", file),
      omitBackground: true,
    });
    if (size !== 180) images.push({ size, bytes });
    console.log(`Rendered ${file}: ${size}×${size}`);
  }
  const header = Buffer.alloc(6 + 16 * images.length);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  let offset = header.length;
  for (let i = 0; i < images.length; i++) {
    const { size, bytes } = images[i];
    const pos = 6 + i * 16;
    header[pos] = size;
    header[pos + 1] = size;
    header.writeUInt16LE(1, pos + 4);
    header.writeUInt16LE(32, pos + 6);
    header.writeUInt32LE(bytes.length, pos + 8);
    header.writeUInt32LE(offset, pos + 12);
    offset += bytes.length;
  }
  await fs.writeFile(
    path.join(root, "public/favicon.ico"),
    Buffer.concat([header, ...images.map((x) => x.bytes)]),
  );
  console.log("Rendered favicon.ico: embedded 32px and 48px PNG images");
} finally {
  await browser.close();
}
