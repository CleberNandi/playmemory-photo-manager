// Bounded queue: at most four IPC requests and 73 waiting demo cards.
let running = 0;
const queue: (() => void)[] = [];
function pump() { while (running < 4 && queue.length) queue.shift()!(); }
export function thumbnailUrl(value: unknown): string | null {
  if (value === null) return null;
  if (!value || typeof value !== "object") throw new Error("invalid thumbnail");
  const data = value as Record<string, unknown>;
  if (data.media_type !== "image/png" || data.width !== 256 || data.height !== 160 ||
      typeof data.base64 !== "string" || data.base64.length > 220000 ||
      !/^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(data.base64) || data.base64.length % 4 !== 0) throw new Error("invalid thumbnail");
  return `data:image/png;base64,${data.base64}`;
}
export function requestThumbnail(assetId: string, receive: (url: string | null) => void): () => void {
  let active = true;
  const task = () => {
    running++;
    void (async () => {
      const deadline = Date.now()+12000;
      while (active) {
        const value = await window.photoManager?.getThumbnail?.(assetId) ?? null;
        if (!value || (value as {status?: string}).status !== "pending") return value;
        if (Date.now()>deadline) return null;
        await new Promise((resolve) => setTimeout(resolve,150));
      }
      return null;
    })()
      .then(thumbnailUrl).then((url) => { if (active) receive(url); })
      .catch(() => { if (active) receive(null); })
      .finally(() => { running--; pump(); });
  };
  if (queue.length < 73) { queue.push(task); pump(); }
  return () => { active = false; const index = queue.indexOf(task); if (index >= 0) queue.splice(index, 1); };
}
