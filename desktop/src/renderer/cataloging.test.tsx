// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CatalogingPanel } from "./CatalogingPanel";
let root: Root; let host: HTMLDivElement;
const status = (state = "running", revision = 1) => ({session_id: "session", operation_id: "operation", revision, state, phase: state === "running" ? "scanning" : null, observed_count: 2, verified_count: 1, excluded_count: 1, total: null, proposal_id: state === "completed" ? "proposal" : null, terminal_reason: null});
beforeEach(() => {
  vi.useFakeTimers(); Object.assign(globalThis, {IS_REACT_ACT_ENVIRONMENT: true});
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
  window.photoManager = {listGallery: vi.fn(), retryGallery: vi.fn(), chooseMediaRoot: vi.fn().mockResolvedValue({root_grant_id: "grant"}), prepareCataloging: vi.fn().mockResolvedValue(status()), getPreparationStatus: vi.fn().mockResolvedValue(status("completed", 2)), cancelPreparation: vi.fn().mockResolvedValue({job: status("cancelling", 2)})};
});
afterEach(async () => {await act(async () => root.unmount()); host.remove(); delete window.photoManager; vi.useRealTimers();});
async function click(text: string) {await act(async () => {[...host.querySelectorAll("button")].find((b) => b.textContent === text)!.click();});}
async function start() {await act(async () => root.render(<CatalogingPanel sessionId="session" />)); await click("Selecionar pasta"); await click("Preparar proposta");}
it("publishes pages only after completion and keeps only one fixed-size page", async () => {
  const pages = vi.fn().mockResolvedValueOnce({proposal_id: "proposal", items: [{candidate_id: "a", relative_path: "nested/a.jpg", state: "eligible", reason: "eligible_jpeg"}], next_cursor: "cursor"}).mockResolvedValueOnce({proposal_id: "proposal", items: [], next_cursor: null});
  window.photoManager!.listCatalogingCandidates = pages;
  await start(); expect(host.textContent).not.toContain("Ver proposta");
  await act(async () => vi.advanceTimersByTimeAsync(250)); await click("Ver proposta");
  expect(pages).toHaveBeenCalledWith("session", "proposal", null, 50); expect(host.textContent).toContain("nested/a.jpg");
  await click("Próxima página"); expect(pages).toHaveBeenLastCalledWith("session", "proposal", "cursor", 50); expect(host.textContent).not.toContain("nested/a.jpg");
});
it("continues monitoring cancellation until terminal and prevents a second selection", async () => {
  window.photoManager!.getPreparationStatus = vi.fn().mockResolvedValue(status("cancelled", 3));
  await start(); await click("Cancelar preparação"); expect(host.textContent).toContain("aguardando encerramento");
  expect([...host.querySelectorAll("button")].find((b) => b.textContent === "Selecionar pasta")!.disabled).toBe(true);
  await act(async () => vi.advanceTimersByTimeAsync(250)); expect(host.textContent).toContain("Preparação cancelada");
});
it("drops late admission after unmount and does not start polling", async () => {
  let resolve!: (value: unknown) => void;
  window.photoManager!.prepareCataloging = vi.fn().mockImplementation(() => new Promise((done) => {resolve = done;}));
  await start(); await act(async () => root.render(<div>Outra sessão</div>));
  await act(async () => {resolve(status());}); await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(window.photoManager!.getPreparationStatus).not.toHaveBeenCalled(); expect(host.textContent).toBe("Outra sessão");
});
it("does not repeat admission after an unknown transport failure", async () => {
  window.photoManager!.prepareCataloging = vi.fn().mockRejectedValue(new Error("unavailable"));
  await start(); expect(host.querySelector('[role="alert"]')?.textContent).toContain("indisponível");
  await act(async () => vi.advanceTimersByTimeAsync(1000)); expect(window.photoManager!.prepareCataloging).toHaveBeenCalledTimes(1);
});
it("cancelled native selection issues no preparation", async () => {
  window.photoManager!.chooseMediaRoot = vi.fn().mockResolvedValue({cancelled: true});
  await act(async () => root.render(<CatalogingPanel sessionId="session" />)); await click("Selecionar pasta");
  expect([...host.querySelectorAll("button")].find((b) => b.textContent === "Preparar proposta")!.disabled).toBe(true);
  expect(window.photoManager!.prepareCataloging).not.toHaveBeenCalled();
});
it("never overlaps status requests while a response is pending", async () => {
  let resolve!: (value: unknown) => void;
  const polling = vi.fn().mockImplementation(() => new Promise((done) => {resolve = done;}));
  window.photoManager!.getPreparationStatus = polling;
  await start(); await act(async () => vi.advanceTimersByTimeAsync(1000)); expect(polling).toHaveBeenCalledTimes(1);
  await act(async () => {resolve(status("completed", 2));}); await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(polling).toHaveBeenCalledTimes(1);
});
