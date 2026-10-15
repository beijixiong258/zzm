import { useState } from "react";
import type { User } from "./types";
import "./account-avatar.css";

export function avatarInitials(name: string): string {
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => Array.from(part)[0] || "")
      .join("")
      .toUpperCase() || "?"
  );
}
export function avatarFileError(file: Pick<File, "size" | "type">): string {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type))
    return "Choose a static PNG, JPEG or WebP image. SVG, GIF and animated images are not supported.";
  if (file.size > 5 * 1024 * 1024) return "The image must be 5 MiB or smaller.";
  if (!file.size) return "The image is empty.";
  return "";
}
export function avatarCrop(width: number, height: number) {
  const size = Math.min(width, height);
  return { x: (width - size) / 2, y: (height - size) / 2, size };
}
/** Local, EXIF-oriented preview; original file goes to the server's authoritative decoder. */
export async function avatarPreview(file: File): Promise<string> {
  const invalid = avatarFileError(file);
  if (invalid) throw new Error(invalid);
  // Reject common animation containers before making a misleading single-frame preview.
  const bytes = new Uint8Array(await file.arrayBuffer());
  const view = new DataView(bytes.buffer);
  const tag = (offset: number) =>
    String.fromCharCode(...bytes.slice(offset, offset + 4));
  if (file.type === "image/png") {
    for (let offset = 8; offset + 12 <= bytes.length;) {
      if (tag(offset + 4) === "acTL")
        throw new Error("Animated images are not supported.");
      offset += view.getUint32(offset) + 12;
    }
  } else if (file.type === "image/webp") {
    for (let offset = 12; offset + 8 <= bytes.length;) {
      if (["ANIM", "ANMF"].includes(tag(offset)))
        throw new Error("Animated images are not supported.");
      const size = view.getUint32(offset + 4, true);
      offset += 8 + size + (size % 2);
    }
  }
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new Error("This file could not be decoded as an image.");
  }
  try {
    if (
      !bitmap.width ||
      !bitmap.height ||
      bitmap.width * bitmap.height > 16_000_000
    )
      throw new Error("The image must contain no more than 16 million pixels.");
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 256;
    const context = canvas.getContext("2d");
    if (!context)
      throw new Error("Image preview is unavailable in this browser.");
    const crop = avatarCrop(bitmap.width, bitmap.height);
    context.drawImage(
      bitmap,
      crop.x,
      crop.y,
      crop.size,
      crop.size,
      0,
      0,
      256,
      256,
    );
    return canvas.toDataURL("image/png");
  } finally {
    bitmap.close();
  }
}
export async function verifyAvatarImage(url: string): Promise<void> {
  const image = new Image();
  image.src = url;
  try {
    await image.decode();
  } catch {
    throw new Error(
      "The saved avatar image could not be loaded. Check the saved result again.",
    );
  }
  if (image.naturalWidth !== 256 || image.naturalHeight !== 256)
    throw new Error("The saved avatar is not the expected 256 × 256 image.");
}
export default function Avatar({
  user,
  large = false,
  className = "",
}: {
  user: Pick<User, "name" | "avatar_url">;
  large?: boolean;
  className?: string;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const url = user.avatar_url;
  return (
    <span
      className={`avatar account-avatar${large ? " large" : ""}${className ? ` ${className}` : ""}`}
    >
      {url && url !== failedUrl ? (
        <img
          src={url}
          alt={`Avatar for ${user.name}`}
          onError={() => setFailedUrl(url)}
        />
      ) : (
        <span role="img" aria-label={`Avatar initials for ${user.name}`}>
          {avatarInitials(user.name)}
        </span>
      )}
    </span>
  );
}
