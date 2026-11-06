// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DesktopMenu } from "./DesktopMenu";
let host: HTMLDivElement; let root: Root;
const action = vi.fn();
beforeEach(async () => {
  Object.assign(globalThis, {IS_REACT_ACT_ENVIRONMENT: true}); action.mockClear();
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
  await act(async () => root.render(<><DesktopMenu label="Arquivo"><button onClick={action}>Abrir</button><button disabled>Indisponível</button><button>Fechar</button></DesktopMenu><DesktopMenu label="Exibir"><button>Miniaturas</button></DesktopMenu><button className="outside">Fora</button><details className="metadata" open><summary>Metadata</summary>Preservada</details></>));
});
afterEach(async () => {await act(async () => root.unmount()); host.remove();});
const menu = (index = 0) => host.querySelectorAll<HTMLDetailsElement>(".desktop-menu")[index];
async function open(index = 0) {await act(async () => {menu(index).open = true; menu(index).dispatchEvent(new Event("toggle"));});}
async function key(key: string) {await act(async () => document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", {key, bubbles: true, cancelable: true})));}
it("closes after an action, outside pointer, focus leaving, and window blur", async () => {
  await open(); await act(async () => menu().querySelector<HTMLButtonElement>("button")!.click());
  expect(action).toHaveBeenCalledOnce(); expect(menu().open).toBe(false);
  await open(); await act(async () => host.querySelector(".outside")!.dispatchEvent(new Event("pointerdown", {bubbles: true})));
  expect(menu().open).toBe(false);
  await open(); await act(async () => {menu().querySelector<HTMLElement>("summary")!.focus(); host.querySelector<HTMLButtonElement>(".outside")!.focus();});
  expect(menu().open).toBe(false);
  await open(); await act(async () => window.dispatchEvent(new Event("blur"))); expect(menu().open).toBe(false);
});
it("keeps just one menu open without closing metadata disclosures", async () => {
  await open(); await open(1);
  expect(menu().open).toBe(false); expect(menu(1).open).toBe(true);
  expect(host.querySelector<HTMLDetailsElement>(".metadata")!.open).toBe(true);
});
it("supports arrow navigation, skips disabled items, and restores focus on Escape", async () => {
  await act(async () => menu().querySelector<HTMLElement>("summary")!.focus());
  await key("ArrowDown"); expect(document.activeElement?.textContent).toBe("Abrir");
  await key("ArrowDown"); expect(document.activeElement?.textContent).toBe("Fechar");
  await key("ArrowRight"); expect(menu().open).toBe(false); expect(menu(1).open).toBe(true);
  await key("ArrowDown"); expect(document.activeElement?.textContent).toBe("Miniaturas");
  const docEscape = vi.fn(); document.addEventListener("keydown", docEscape);
  await key("Escape"); document.removeEventListener("keydown", docEscape);
  expect(menu(1).open).toBe(false); expect(document.activeElement?.textContent).toBe("Exibir");
  expect(docEscape).not.toHaveBeenCalled();
});
