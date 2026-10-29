import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AvailabilityIndicator, getAvailabilityLabel } from "./AvailabilityIndicator";
import { formatItemCount, Sidebar, Status } from "./App";
import { MediaCard } from "./MediaCard";
import type { Availability, GalleryItem } from "./types";
const item: GalleryItem = { asset_id: "00000000-0000-4000-8000-000000000001", kind: "photo", media_type: null, created_at: "2026-01-01T00:00:00Z", availability: "offline", annotation: { rating: null, favorite: false, title: "Retrato sintético" }, representative_location: { relative_path: "fixtures/retrato.jpg", root_display_name: "Fixtures" } };
describe("renderer visual components", () => {
  it("renders availability as text instead of relying on color", () => { const states: Availability[] = ["available", "offline", "unavailable", "no_location"]; for (const availability of states) { const markup = renderToStaticMarkup(<AvailabilityIndicator availability={availability} />); expect(markup).toContain(getAvailabilityLabel(availability)); expect(markup).toContain(`availability-${availability}`); } });
  it("keeps informational cards out of the tab order", () => { const markup = renderToStaticMarkup(<MediaCard item={item} />); expect(markup).not.toContain('tabindex='); expect(markup).toContain('role="listitem"'); expect(markup).toContain("Retrato sintético"); expect(markup).not.toContain("aria-label"); expect(markup).not.toContain(item.asset_id); });
  it("marks active navigation and labels unavailable destinations", () => { const markup = renderToStaticMarkup(<Sidebar />); expect(markup).toContain('aria-current="page"'); expect(markup).toContain('aria-label="Álbuns — em breve"'); expect(markup).toContain("Seus originais não são alterados."); });
  it("uses an alert only for a recoverable error", () => { expect(renderToStaticMarkup(<Status icon="photo" title="Vazia" body="Sem itens" />)).toContain('role="status"'); expect(renderToStaticMarkup(<Status icon="photo" title="Falha" body="Tente novamente" tone="error" />)).toContain('role="alert"'); });
  it("formats item counts", () => { expect(formatItemCount(1)).toBe("1 item carregado"); expect(formatItemCount(24)).toBe("24 itens carregados"); });
});

 it.each([null, "", "   "])("falls back from blank title %s", (title) => {
   expect(renderToStaticMarkup(<MediaCard item={{...item, annotation: {...item.annotation, title}}} />)).toContain("fixtures/retrato.jpg");
   expect(renderToStaticMarkup(<MediaCard item={{...item, annotation: {...item.annotation, title}, representative_location: {...item.representative_location!, relative_path: "   "}}} />)).toContain("Sem título");
 });
