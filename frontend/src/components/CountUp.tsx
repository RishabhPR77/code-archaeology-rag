import { useEffect, useState } from "react";

import { formatNumber } from "../lib/utils";

const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/** A number that counts up from 0 when it first appears (or jumps straight there with reduced motion). */
export function CountUp({ value, ms = 800 }: { value: number; ms?: number }) {
  const [shown, setShown] = useState(() => (reduced() ? value : 0));
  useEffect(() => {
    if (reduced() || value === 0) {
      setShown(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      setShown(Math.round(value * (1 - (1 - t) ** 3)));   // ease out
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, ms]);
  return <>{formatNumber(shown)}</>;
}
