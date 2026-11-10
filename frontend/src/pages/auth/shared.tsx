import { useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { AnswerPreview } from "../../components/AnswerPreview";
import { GitHubIcon, GoogleIcon, Logo, ThemeToggle } from "../../components/brand";
import { Button, Input, Label } from "../../components/ui";
import { meKey } from "../../lib/auth";
import { useAuthConfig } from "../../lib/queries";
import type { Me } from "../../lib/types";
import { cn } from "../../lib/utils";

export const OAUTH_ERRORS: Record<string, string> = {
  github_denied: "GitHub sign-in was cancelled.",
  github_state: "That sign-in attempt expired. Please try again.",
  github_token: "GitHub didn't accept the sign-in. Please try again.",
  github_unavailable: "Couldn't reach GitHub. Please try again.",
  github_no_email: "Your GitHub account has no verified email address we can read.",
  google_denied: "Google sign-in was cancelled.",
  google_state: "That sign-in attempt expired. Please try again.",
  google_token: "Google didn't accept the sign-in. Please try again.",
  google_unavailable: "Couldn't reach Google. Please try again.",
  google_unverified: "Your Google account's email address isn't verified.",
};

// The address a code was just sent to, so the code page survives a reload before there's a session
const PENDING_EMAIL = "ca_pending_email";
export const pendingEmail = {
  get: () => { try { return sessionStorage.getItem(PENDING_EMAIL) ?? ""; } catch { return ""; } },
  set: (email: string) => { try { sessionStorage.setItem(PENDING_EMAIL, email); } catch { /* private mode */ } },
  clear: () => { try { sessionStorage.removeItem(PENDING_EMAIL); } catch { /* private mode */ } },
};

export function AuthShell({ title, subtitle, children, footer }: {
  title: string; subtitle: ReactNode; children: ReactNode; footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-full bg-surface">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between px-4 py-4 sm:px-8">
          <Logo />
          <ThemeToggle />
        </header>
        <main className="flex flex-1 items-center justify-center px-4 py-10">
          <div className="w-full max-w-sm animate-fade-up">
            <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
            <p className="mt-1.5 text-sm text-muted">{subtitle}</p>
            <div className="mt-8">{children}</div>
            {footer && <p className="mt-8 text-center text-[13px] text-muted">{footer}</p>}
            <p className="mt-4 text-center text-xs text-subtle">
              By continuing you agree to the <Link to="/terms" className="underline hover:text-text">Terms</Link> and{" "}
              <Link to="/privacy" className="underline hover:text-text">Privacy Policy</Link>.
            </p>
          </div>
        </main>
      </div>
      <aside className="hidden w-[46%] max-w-3xl items-center justify-center border-l border-border bg-accent-soft p-10 lg:flex">
        <div className="w-full max-w-md">
          <p className="mb-5 text-xl font-bold tracking-tight">Ask a repository why its code was written.</p>
          <AnswerPreview />
        </div>
      </aside>
    </div>
  );
}

export function OAuthButtons() {
  const { data } = useAuthConfig();
  if (!data?.google_enabled && !data?.github_enabled) return null;
  // Full-page navigations: the server redirects to the provider and back
  return (
    <>
      <div className="space-y-2.5">
        {data.google_enabled && (
          <a href="/api/auth/google/login" className="block">
            <Button type="button" variant="secondary" size="lg" className="w-full">
              <GoogleIcon /> Continue with Google
            </Button>
          </a>
        )}
        {data.github_enabled && (
          <a href="/api/auth/github/login" className="block">
            <Button type="button" variant="secondary" size="lg" className="w-full">
              <GitHubIcon /> Continue with GitHub
            </Button>
          </a>
        )}
      </div>
      <div className="my-6 flex items-center gap-3 text-xs text-subtle">
        <div className="h-px flex-1 bg-border" /> or with email <div className="h-px flex-1 bg-border" />
      </div>
    </>
  );
}

export function PasswordInput({ id, value, onChange, autoComplete, invalid }: {
  id: string; value: string; onChange: (v: string) => void; autoComplete: string; invalid?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input id={id} type={show ? "text" : "password"} required minLength={8} value={value} aria-invalid={invalid}
             autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)}
             className={cn("pr-10", invalid && "border-danger focus-visible:ring-danger/30")} />
      <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-subtle hover:text-text cursor-pointer">
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}

/** 0 (too short) to 3 (strong). Length matters most; the server also refuses well-known passwords. */
export function passwordStrength(pw: string): number {
  if (pw.length < 8) return 0;
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  return Math.min(3, 1 + (pw.length >= 12 ? 1 : 0) + (pw.length >= 16 || kinds >= 3 ? 1 : 0));
}

const STRENGTH = ["Too short", "Okay", "Good", "Strong"];

/** A new password typed twice, with a strength meter. `valid` is true when both match and are long enough. */
export function NewPasswordFields({ password, confirm, onPassword, onConfirm, label = "Password" }: {
  password: string; confirm: string; onPassword: (v: string) => void; onConfirm: (v: string) => void; label?: string;
}) {
  const strength = passwordStrength(password);
  const mismatch = confirm.length > 0 && confirm !== password;
  return (
    <>
      <div>
        <Label htmlFor="new-password" hint="At least 8 characters. A few words together is easy to remember.">{label}</Label>
        <PasswordInput id="new-password" value={password} onChange={onPassword} autoComplete="new-password" />
        {password && (
          <div className="mt-2 flex items-center gap-2" aria-live="polite">
            <div className="flex flex-1 gap-1">
              {[1, 2, 3].map((i) => (
                <span key={i} className={cn("h-1 flex-1 rounded-full bg-border transition-colors",
                  strength >= i && (strength === 1 ? "bg-warning" : "bg-accent"))} />
              ))}
            </div>
            <span className="w-16 text-right text-xs text-muted">{STRENGTH[strength]}</span>
          </div>
        )}
      </div>
      <div>
        <Label htmlFor="confirm-password">Confirm {label.toLowerCase()}</Label>
        <PasswordInput id="confirm-password" value={confirm} onChange={onConfirm} autoComplete="new-password"
                       invalid={mismatch} />
        {mismatch && <p className="mt-1.5 text-xs text-danger">The passwords don't match.</p>}
      </div>
    </>
  );
}

export const passwordsReady = (password: string, confirm: string) => password.length >= 8 && password === confirm;

export function useAuthSuccess() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/app";
  return (me: Me) => {
    qc.clear();   // nothing cached for a previous account (or the demo) carries over
    qc.setQueryData(meKey, me);
    pendingEmail.clear();
    navigate(from, { replace: true });
  };
}
