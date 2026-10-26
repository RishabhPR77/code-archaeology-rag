import { useEffect, useState } from "react";

const TOKENS = ["accent", "muted", "subtle", "border", "surface", "surface-2", "text", "success", "danger"] as const;
type Token = (typeof TOKENS)[number];

function read(): Record<Token, string> {
  const style = getComputedStyle(document.documentElement);
  return Object.fromEntries(TOKENS.map((t) => [t, style.getPropertyValue(`--${t}`).trim()])) as Record<Token, string>;
}

/** Resolved theme colours for SVG charts, which can't use CSS variables in attributes. */
export function useThemeColors() {
  const [colors, setColors] = useState(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setColors(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return colors;
}

export function tooltipStyle(c: Record<Token, string>) {
  return {
    contentStyle: {
      background: c.surface, border: `1px solid ${c.border}`, borderRadius: 10, fontSize: 12,
      color: c.text, boxShadow: "0 8px 24px rgb(0 0 0 / 0.18)",
    },
    labelStyle: { color: c.muted, marginBottom: 4 },
    itemStyle: { color: c.text },
    cursor: { fill: c["surface-2"] },
  };
}
