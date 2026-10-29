import type { Availability } from "./types";
const labels: Record<Availability, string> = { available: "Disponível", offline: "Raiz offline", unavailable: "Arquivo indisponível", no_location: "Sem localização" };
export function AvailabilityIndicator({ availability }: { availability: Availability }) {
  return <span className={`availability availability-${availability}`}><span className="availability-dot" aria-hidden="true" />{labels[availability]}</span>;
}
export function getAvailabilityLabel(availability: Availability): string { return labels[availability]; }
