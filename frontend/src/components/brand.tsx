import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import type { ProviderId } from "../lib/types";
import { cn, PROVIDER_STYLE } from "../lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <circle cx="11" cy="10" r="3" fill="var(--accent-fg)" />
      <circle cx="11" cy="22" r="3" fill="var(--accent-fg)" />
      <circle cx="22" cy="16" r="3" fill="var(--accent-fg)" />
      <path d="M11 13v6M13.5 11.5l6 3" stroke="var(--accent-fg)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ to = "/", className }: { to?: string; className?: string }) {
  return (
    <Link to={to} aria-label="Code Archaeologist home"
          className={cn("flex shrink-0 items-center gap-2.5 font-semibold tracking-tight", className)}>
      <LogoMark />
      {/* The mark alone carries the brand on the narrowest phones */}
      <span className="whitespace-nowrap text-[15px] max-[400px]:hidden">Code Archaeologist</span>
    </Link>
  );
}

export function ProviderMark({ id, className }: { id: ProviderId; className?: string }) {
  const { mono, color } = PROVIDER_STYLE[id];
  return (
    <span
      className={cn("grid size-8 shrink-0 place-items-center rounded-lg font-mono text-[11px] font-bold text-white", className)}
      style={{ background: color }}
      aria-hidden
    >
      {mono}
    </span>
  );
}

export function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("ca-theme", dark ? "dark" : "light");
    } catch {
      /* storage unavailable — theme still applies for this visit */
    }
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

export function ThemeToggle({ className }: { className?: string }) {
  const { dark, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className={cn("grid size-9 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-text cursor-pointer", className)}
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}

export function GitHubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={cn("size-4", className)} aria-hidden>
      <path d="M12 .5C5.65.5.5 5.65.5 12a11.5 11.5 0 0 0 7.86 10.92c.58.1.79-.25.79-.56v-2c-3.2.7-3.87-1.37-3.87-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.4-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}
