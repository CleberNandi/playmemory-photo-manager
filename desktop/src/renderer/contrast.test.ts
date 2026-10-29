import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
const css = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
function token(name: string): string {
  const match = css.match(new RegExp(`--${name}: (#[a-f0-9]{6})`));
  if (!match) throw new Error(`missing token ${name}`);
  return match[1];
}
function availabilityColor(state: string): string {
  const declaration = css.match(new RegExp(`\\.availability-${state} \\{ color: ([^;]+);`))?.[1];
  if (!declaration) throw new Error(`missing availability style ${state}`);
  return declaration.startsWith("var(") ? token(declaration.slice(6, -1)) : declaration;
}
function luminance(hex: string): number {
  const rgb = hex.slice(1).match(/../g)!.map((part) => parseInt(part, 16) / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
}
function contrast(a: string, b: string): number { const x = luminance(a); const y = luminance(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); }
it("availability text meets AA on the actual canvas", () => {
  for (const color of ["available", "offline", "unavailable", "no_location"].map(availabilityColor)) expect(contrast(color, token("color-canvas"))).toBeGreaterThanOrEqual(4.5);
});
it("focus rings contrast with adjacent surfaces", () => {
  for (const surface of [token("color-canvas"), token("color-surface")]) expect(contrast(token("focus-ring"), surface)).toBeGreaterThanOrEqual(3);
  for (const surface of [token("color-sidebar"), token("color-sidebar-active")]) expect(contrast("#e0aa56", surface)).toBeGreaterThanOrEqual(3);
  expect(css).toContain(".sidebar :focus-visible { outline-color: #e0aa56; }");
});
