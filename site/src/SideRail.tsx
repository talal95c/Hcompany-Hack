import { useEffect, useState } from "react";

const ITEMS = [
  { id: "top", label: "Home", d: "M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z" },
  { id: "pricing", label: "Pricing", d: "M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8zM7.5 7.5h.01" },
  { id: "features", label: "Features", d: "M12 2l2.9 6.9L22 9.5l-5.5 4.8L18.2 21 12 17.3 5.8 21l1.7-6.7L2 9.5l7.1-.6z" },
  { id: "contact", label: "Contact", d: "M3 5h18v14H3zM3 6l9 7 9-7" },
];

export function SideRail() {
  const [active, setActive] = useState("top");
  useEffect(() => {
    const onScroll = () => {
      let cur = "top";
      for (const it of ITEMS) {
        const el = document.getElementById(it.id);
        if (el && el.getBoundingClientRect().top < innerHeight * 0.45) cur = it.id;
      }
      if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) cur = "contact";
      setActive(cur);
    };
    onScroll();
    addEventListener("scroll", onScroll, { passive: true });
    return () => removeEventListener("scroll", onScroll);
  }, []);
  return (
    <aside className="rail" aria-label="On this page">
      <span className="rail-title">On this page</span>
      {ITEMS.map((it) => (
        <a
          key={it.id}
          href={`#${it.id}`}
          className={`rail-item${active === it.id ? " on" : ""}`}
          data-cursor-label={`go to ${it.label.toLowerCase()}`}
        >
          <svg viewBox="0 0 24 24" aria-hidden><path d={it.d} /></svg>
          <span>{it.label}</span>
        </a>
      ))}
    </aside>
  );
}
