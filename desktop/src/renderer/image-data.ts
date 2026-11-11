const chunkSize = 96 * 1024;
const maximumSize = 16 * 1024 * 1024;
const base64 = /^[A-Za-z0-9+/]+={0,2}$/;

async function read(
  assetId: string, variant: "dimensions" | "original", active: () => boolean, offset?: number,
) {
  const deadline = Date.now() + 12000;
  while (active() && Date.now() < deadline) {
    const value = await window.photoManager?.getPreview?.(assetId, variant, offset) as Record<string, unknown> | null;
    if (!active()) return null;
    if (value?.status !== "pending") return value;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  return null;
}

export async function readDimensions(assetId: string, active: () => boolean) {
  const value = await read(assetId, "dimensions", active);
  const width = value?.width;
  const height = value?.height;
  if (typeof width !== "number" || typeof height !== "number"
    || !Number.isInteger(width) || !Number.isInteger(height)
    || width <= 0 || height <= 0 || width * height > 40_000_000) return null;
  return {width, height};
}

export async function readOriginal(assetId: string, active: () => boolean) {
  const first = await read(assetId, "original", active, 0);
  const total = first?.total;
  const digest = first?.digest;
  if (typeof total !== "number" || !Number.isInteger(total) || total <= 0 || total > maximumSize
    || typeof digest !== "string" || !/^[0-9a-f]{64}$/.test(digest)) return null;
  const chunks: string[] = [];
  for (let offset = 0; offset < total && active(); offset += chunkSize) {
    const value = offset === 0 ? first : await read(assetId, "original", active, offset);
    const data = value?.base64;
    const size = Math.min(chunkSize, total - offset);
    const padding = (3 - size % 3) % 3;
    if (value?.digest !== digest || value.total !== total || typeof data !== "string"
      || data.length !== 4 * Math.ceil(size / 3) || !base64.test(data)
      || (data.match(/=*$/)?.[0].length ?? 0) !== padding) return null;
    chunks.push(data);
  }
  if (!active() || !chunks[0]?.startsWith("/9j/")) return null;
  return `data:image/jpeg;base64,${chunks.join("")}`;
}
