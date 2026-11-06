import { useEffect, useRef, type ReactNode } from "react";

// Only application menus participate; metadata disclosure panels remain independent.
export function DesktopMenu({label, children}: {label: string; children: ReactNode}) {
  const ref = useRef<HTMLDetailsElement>(null);
  const menus = () => [...document.querySelectorAll<HTMLDetailsElement>(".desktop-menu")];
  const trigger = (menu: HTMLDetailsElement) => menu.querySelector<HTMLElement>("summary")!;
  const close = (restoreFocus = false) => {
    const menu = ref.current;
    if (!menu) return;
    menu.open = false;
    if (restoreFocus) trigger(menu).focus();
  };
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !ref.current?.contains(event.target)) ref.current?.removeAttribute("open");
    };
    const blur = () => ref.current?.removeAttribute("open");
    document.addEventListener("pointerdown", outside, true);
    window.addEventListener("blur", blur);
    return () => {document.removeEventListener("pointerdown", outside, true); window.removeEventListener("blur", blur);};
  }, []);
  const open = () => {
    const menu = ref.current!;
    for (const other of menus()) if (other !== menu) other.open = false;
    menu.open = true;
  };
  return <details ref={ref} className="desktop-menu" onToggle={(event) => {
    if (event.currentTarget.open) for (const other of menus()) if (other !== event.currentTarget) other.open = false;
  }} onBlur={(event) => {if (!event.currentTarget.contains(event.relatedTarget as Node | null)) close();}}
  onClick={(event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("button");
    if (button && !button.disabled) close(true);
  }} onKeyDown={(event) => {
    const menu = ref.current!;
    const buttons = [...menu.querySelectorAll<HTMLButtonElement>(".desktop-menu-popup button:not(:disabled)")];
    if (event.key === "Escape" && menu.open) {event.preventDefault(); event.stopPropagation(); close(true);}
    else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault(); open();
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : event.key === "ArrowDown" ? (index + 1) % buttons.length : (index < 0 ? buttons.length - 1 : (index - 1 + buttons.length) % buttons.length);
      buttons[next]?.focus();
    } else if (["ArrowRight", "ArrowLeft"].includes(event.key)) {
      event.preventDefault();
      const all = menus(); const index = all.indexOf(menu);
      const next = all[(index + (event.key === "ArrowRight" ? 1 : -1) + all.length) % all.length];
      const wasOpen = menu.open; close(); trigger(next).focus();
      if (wasOpen) next.open = true;
    }
  }}>
    <summary>{label}</summary>
    <div className="desktop-menu-popup">{children}</div>
  </details>;
}
