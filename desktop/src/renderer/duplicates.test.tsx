// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { Coverage, DuplicatesView } from "./DuplicatesView";
import type { DuplicateGroup, DuplicateGroupPage, DuplicateListPage, DuplicateResult } from "./types";
const group = (key = "one"): DuplicateGroup => ({group_key: key, sha256: "0".repeat(64), byte_size: "9007199254740993", evidence_fingerprint: null, occurrence_count: 105, physical_copy_count: 104, blocks: ["hardlink", "identity_conflict"], plan_state: null, review: null});
const list = (groups = [group()]): DuplicateListPage => ({version: 1, snapshot_id: "session", source: "synthetic_fixture", observed_at: null, freshness: "synthetic", coverage: "partial", issues: [], eligible_location_count: 105, hashed_location_count: 0, total_count: groups.length, next_cursor: null, groups});
const members = (key = "one", ids = ["first"]): DuplicateGroupPage => ({...list(), group: group(key), total_count: ids.length, members: ids.map((id) => ({asset_id: id, location_id: id, library_root_id: "root", root_display_name: "Raiz <b>literal</b>", relative_path: "界/" + "longo/".repeat(80), location_source: "projection_fixture", hardlinked: true, identity_conflict: true, protected: null, blocks: ["hardlink"]}))});
let host: HTMLDivElement; let root: Root;
beforeEach(() => {Object.assign(globalThis, {IS_REACT_ACT_ENVIRONMENT: true}); host = document.createElement("div"); document.body.append(host); root = createRoot(host);});
afterEach(async () => {await act(async () => root.unmount()); host.remove(); delete window.photoManager;});
const mount = async () => {await act(async () => root.render(<App />));};
const click = async (selector: string) => {await act(async () => host.querySelector<HTMLButtonElement>(selector)!.click());};
const navigate = async () => click('[aria-label="Duplicatas exatas"]');
function bridge() {
  window.photoManager = {listGallery: vi.fn().mockResolvedValue({items: [], next_cursor: null, has_more: false}), retryGallery: vi.fn(), listDuplicates: vi.fn().mockResolvedValue({status: "ready", page: list()}), getDuplicateGroup: vi.fn().mockResolvedValue({status: "ready", page: members()})};
  return window.photoManager;
}
it("navigates without reloading gallery, presents synthetic facts and restores group focus", async () => {
  const b = bridge(); await mount(); await navigate();
  expect(host.textContent).toContain("Dados sintéticos"); expect(host.textContent).toContain("Cobertura parcial");
  await click('.group-select');
  expect(host.querySelector('.duplicate-group')?.textContent).toContain("Proteção: desconhecida");
  expect(host.querySelector('.duplicate-group')?.textContent).toContain("Ocorrência simulada somente nesta projeção");
  expect(host.querySelector('.duplicate-group')?.textContent).toContain("Raiz <b>literal</b>");
  expect(host.querySelector('.duplicate-group b')).toBeNull();
  expect(document.activeElement).toBe(host.querySelector('.close-group'));
  await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'})));
  expect(host.querySelector('.duplicate-group')).toBeNull(); expect(document.activeElement).toBe(host.querySelector('.group-select'));
  await click('[aria-label="Biblioteca"]');
  expect(b.listGallery).toHaveBeenCalledOnce();
});
it("shows analysis_not_available without retry or restart", async () => {
  const b = bridge(); b.listDuplicates = vi.fn().mockResolvedValue({status: 'analysis_not_available'});
  await mount(); await navigate();
  expect(host.querySelector('.duplicates-view')?.textContent).toContain("Nenhuma mídia foi analisada");
  expect(host.querySelector('.duplicates-view button')).toBeNull(); expect(b.retryGallery).not.toHaveBeenCalled();
});
it.each(['complete', 'partial', 'unavailable'] as const)("explains zero groups with %s coverage", async (coverage) => {
  bridge().listDuplicates = vi.fn().mockResolvedValue({status: 'ready', page: {...list([]), coverage}});
  await mount(); await navigate();
  expect(host.textContent).toContain(coverage === 'complete' ? 'Nenhum grupo no escopo sintético analisado' : 'a cobertura não permite concluir ausência');
});
it("shows global issues, preserves exact integers and labels stale historical review", async () => {
  const g = {...group(), review: {decision_id: 'd', status: 'stale' as const, keep_location_id: 'm', reason: '<script>literal</script>'}, plan_state: 'stale' as const};
  bridge().listDuplicates = vi.fn().mockResolvedValue({status: 'ready', page: list([g])});
  await mount(); await navigate();
  expect(host.textContent).toContain('9007199254740993'); expect(host.textContent).toContain('histórica desatualizada'); expect(host.querySelector('script')).toBeNull();
  await act(async () => root.render(<Coverage page={{...list(), issues: [{kind: 'root_offline', asset_id: 'a', location_id: 'l', library_root_id: 'r', relative_path: 'ação.jpg'}]}} />));
  expect(host.textContent).toContain('Raiz offline · ação.jpg');
});
it("blocks duplicate pagination, preserves pages after sanitized errors and retries exact cursor", async () => {
  const b = bridge();
  b.getDuplicateGroup = vi.fn().mockResolvedValueOnce({status: 'ready', page: {...members(), next_cursor: 'opaque', total_count: 2}}).mockRejectedValueOnce(new Error('/private/secret'));
  let finish!: (value: DuplicateResult<DuplicateGroupPage>) => void;
  (b.getDuplicateGroup as ReturnType<typeof vi.fn>).mockImplementationOnce(() => new Promise((resolve) => {finish = resolve;}));
  await mount(); await navigate(); await click('.group-select'); await click('.more-members');
  expect(host.querySelectorAll('.duplicate-members > li')).toHaveLength(1); expect(host.textContent).not.toContain('/private');
  await act(async () => {const button = host.querySelector<HTMLButtonElement>('.duplicate-group [role=alert] button')!; button.click(); button.click();});
  expect(b.getDuplicateGroup).toHaveBeenCalledTimes(3); expect(host.textContent).toContain('Carregando membros…');
  await act(async () => finish({status: 'ready', page: {...members('one', ['last']), total_count: 2}}));
  expect(host.querySelectorAll('.duplicate-members > li')).toHaveLength(2);
  expect(b.getDuplicateGroup).toHaveBeenLastCalledWith({snapshotId: 'session', groupKey: 'one', pageSize: 24, after: 'opaque'});
});
it("paginates group summaries and preserves them when opening a group", async () => {
  const b = bridge(); b.listDuplicates = vi.fn().mockResolvedValueOnce({status: 'ready', page: {...list(), next_cursor: 'groups', total_count: 2}}).mockResolvedValueOnce({status: 'ready', page: {...list([group('two')]), total_count: 2}});
  await mount(); await navigate(); await click('.more-groups');
  expect(host.querySelectorAll('.group-select')).toHaveLength(2);
  expect(b.listDuplicates).toHaveBeenLastCalledWith({pageSize: 2, after: 'groups'});
  await click('.group-select'); expect(host.querySelectorAll('.group-select')).toHaveLength(2);
});
it("discards late responses on group switch, close, navigation and backend restart", async () => {
  const b = bridge(); b.listDuplicates = vi.fn().mockResolvedValue({status: 'ready', page: list([group(), group('two')])});
  let finish!: (value: DuplicateResult<DuplicateGroupPage>) => void;
  b.getDuplicateGroup = vi.fn().mockImplementationOnce(() => new Promise((resolve) => {finish = resolve;})).mockResolvedValue({status: 'ready', page: members('two', ['second'])});
  let reset!: () => void; b.onBackendReset = (listener) => {reset = listener; return vi.fn();};
  await mount(); await navigate(); await click('.group-select');
  await click('.group-select[aria-pressed="false"]');
  await act(async () => finish({status: 'ready', page: members()}));
  expect(host.querySelector('.duplicate-members')?.textContent).toContain('second'); expect(host.querySelector('.duplicate-members')?.textContent).not.toContain('first');
  await act(async () => reset()); expect(host.querySelector('.duplicate-group')).toBeNull();
  expect(b.listDuplicates).toHaveBeenCalledTimes(2);
  await click('[aria-label="Biblioteca"]'); expect(host.querySelector('.duplicates-view')).toBeNull();
});
it("keeps gallery items through navigation and opens D02C details from a member", async () => {
  const b = bridge(); b.listGallery = vi.fn().mockResolvedValue({items: [{asset_id:'gallery', kind:'photo', media_type:null, created_at:'', availability:'offline', annotation:{rating:null, favorite:false, title:'Galeria preservada'}, representative_location:null}], next_cursor:null, has_more:false});
  b.getAssetDetails = vi.fn().mockResolvedValue({status: 'not_found'});
  await mount(); await navigate(); await click('.group-select'); await click('.member-details');
  expect(b.getAssetDetails).toHaveBeenCalledWith('first'); expect(host.querySelector('.asset-details')).not.toBeNull();
  await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'})));
  expect(host.querySelector('.asset-details')).toBeNull(); expect(host.querySelector('.duplicate-group')).not.toBeNull();
  expect(document.activeElement).toBe(host.querySelector('.member-details'));
  await click('[aria-label="Biblioteca"]'); expect(host.querySelector('.media-card h3')?.textContent).toContain('Galeria preservada');
});
it("shows loading and ignores a list response after unmount", async () => {
  let finish!: (v: DuplicateResult<DuplicateListPage>) => void;
  bridge().listDuplicates = () => new Promise((resolve) => {finish = resolve;});
  await act(async () => root.render(<DuplicatesView onAsset={vi.fn()} detailsOpen={false} onClearAsset={vi.fn()} />));
  expect(host.textContent).toContain('Carregando grupos…');
  await act(async () => root.render(<p>Fechado</p>));
  await act(async () => finish({status: 'ready', page: list()})); expect(host.textContent).toBe('Fechado');
});
it("drops a pending member page when the group closes", async () => {
  const b = bridge();
  let finish!: (v: DuplicateResult<DuplicateGroupPage>) => void;
  b.getDuplicateGroup = vi.fn().mockResolvedValueOnce({status: 'ready', page: {...members(), next_cursor: 'next', total_count: 2}}).mockImplementationOnce(() => new Promise((resolve) => {finish = resolve;}));
  await mount(); await navigate(); await click('.group-select'); await click('.more-members'); await click('.close-group');
  await act(async () => finish({status: 'ready', page: members('one', ['late'])}));
  expect(host.querySelector('.duplicate-group')).toBeNull(); expect(document.activeElement).toBe(host.querySelector('.group-select'));
});
it("reopens a stale snapshot without mixing its pages", async () => {
  const b = bridge();
  b.listDuplicates = vi.fn().mockResolvedValueOnce({status: 'ready', page: {...list(), next_cursor: 'old'}}).mockResolvedValueOnce({status: 'stale_snapshot'}).mockResolvedValueOnce({status: 'ready', page: {...list([group('new')]), snapshot_id: 'new-session'}});
  await mount(); await navigate(); await click('.more-groups');
  expect(host.textContent).toContain('A sessão de demonstração mudou');
  await click('.duplicates-view [role=alert] button');
  expect(host.querySelectorAll('.group-select')).toHaveLength(1);
  expect(host.textContent).not.toContain('A sessão de demonstração mudou');
});
