// 在本机渲染原始矢量网站图标，无需外部素材或网络。
import { chromium } from "@playwright/test";
import { Buffer } from "node:buffer";
import fs from "node:fs/promises";
import path from "node:path";

interface IconImage {
  size: number;
  bytes: Buffer;
}

function createIconFile(images: IconImage[]): Buffer {
  const header = Buffer.alloc(6 + 16 * images.length);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  let imageOffset = header.length;

  for (const [index, image] of images.entries()) {
    const entryPosition = 6 + index * 16;
    header[entryPosition] = image.size;
    header[entryPosition + 1] = image.size;
    header.writeUInt16LE(1, entryPosition + 4);
    header.writeUInt16LE(32, entryPosition + 6);
    header.writeUInt32LE(image.bytes.length, entryPosition + 8);
    header.writeUInt32LE(imageOffset, entryPosition + 12);
    imageOffset += image.bytes.length;
  }

  return Buffer.concat([header, ...images.map((image) => image.bytes)]);
}

async function generateBrandAssets(): Promise<void> {
  const projectRoot = path.resolve(import.meta.dirname, "..");
  const svg = await fs.readFile(path.join(projectRoot, "public/favicon.svg"), "utf8");
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
    const images: IconImage[] = [];
    for (const size of [32, 48, 180]) {
      await page.setViewportSize({ width: size, height: size });
      await page.setContent(
        `<style>html,body{margin:0}svg{width:${size}px;height:${size}px;display:block}</style>${svg}`,
      );
      const fileName = size === 180 ? "apple-touch-icon.png" : `favicon-${size}.png`;
      const bytes = await page.screenshot({
        path: path.join(projectRoot, "public", fileName),
        omitBackground: true,
      });
      if (size !== 180) images.push({ size, bytes });
      console.log(`已生成 ${fileName}：${size}×${size}`);
    }

    await fs.writeFile(
      path.join(projectRoot, "public/favicon.ico"),
      createIconFile(images),
    );
    console.log("已生成 favicon.ico：包含 32px 和 48px PNG 图像");
  } finally {
    await browser.close();
  }
}

await generateBrandAssets();
