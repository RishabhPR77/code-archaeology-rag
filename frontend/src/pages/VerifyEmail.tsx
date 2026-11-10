import { useMutation } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { toast } from "sonner";

import { Logo, ThemeToggle } from "../components/brand";
import { Button, ErrorNotice, Input } from "../components/ui";
import { api } from "../lib/api";
import { useMe, useSignOut } from "../lib/auth";
import { pendingEmail, useAuthSuccess } from "./auth/shared";

const RESEND_SECONDS = 60;

/** Enter the emailed code. Just after sign-up there's no session yet: the code is checked against the
 *  address it was sent to, and a correct code signs the person in. Someone signed in with a password
 *  but not yet confirmed lands here too. */
export default function VerifyEmail() {
  const { data } = useMe();
  const location = useLocation();
  const state = location.state as { email?: string; resendIn?: number } | null;
  const signedIn = data && !data.user.is_demo ? data.user : null;
  const email = signedIn?.email ?? state?.email ?? pendingEmail.get();
  const [code, setCode] = useState("");
  // The server knows when the last code went out, so a reload doesn't restart the wait
  const [cooldown, setCooldown] = useState(signedIn?.code_resend_in ?? state?.resendIn ?? 0);
  const navigate = useNavigate();
  const signOut = useSignOut();
  const onSuccess = useAuthSuccess();

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const verify = useMutation({
    mutationFn: () => api.verifyEmail(code, signedIn ? undefined : email),
    onSuccess: (me) => {
      toast.success("Email confirmed", { description: "Welcome to Code Archaeologist." });
      onSuccess(me);
    },
  });
  const resend = useMutation({
    mutationFn: () => api.resendCode(signedIn ? undefined : email),
    onSuccess: () => {
      setCooldown(RESEND_SECONDS);
      setCode("");
      verify.reset();
      toast.success("New code sent", { description: `Check ${email}` });
    },
  });

  if (signedIn?.email_verified) return <Navigate to="/app" replace />;
  if (!email) return <Navigate to="/register" replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (code.length === 6) verify.mutate();
  };

  return (
    <div className="flex min-h-full flex-col bg-surface">
      <header className="flex items-center justify-between px-4 py-4 sm:px-8">
        <Logo />
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm animate-fade-up">
          <div className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent">
            <MailCheck className="size-5" />
          </div>
          <h1 className="mt-5 text-2xl font-semibold tracking-tight">Check your email</h1>
          <p className="mt-1.5 text-sm text-muted">
            We sent a 6-digit code to <span className="font-medium text-text">{email}</span>.
            It expires in 10 minutes. If you already have an account, the email says so instead.
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              placeholder="000000"
              aria-label="6-digit code"
              className="h-14 text-center font-mono text-2xl tracking-[0.5em]"
            />
            {verify.error && <ErrorNotice error={verify.error} />}
            {resend.error && <ErrorNotice error={resend.error} />}
            <Button type="submit" size="lg" className="w-full" loading={verify.isPending} disabled={code.length !== 6}>
              Confirm email
            </Button>
          </form>

          <div className="mt-6 flex items-center justify-between text-[13px]">
            <button
              type="button"
              onClick={() => resend.mutate()}
              disabled={cooldown > 0 || resend.isPending}
              className="font-medium text-accent hover:underline disabled:text-subtle disabled:no-underline cursor-pointer"
            >
              {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
            </button>
            <button
              type="button"
              onClick={async () => { pendingEmail.clear(); if (signedIn) await signOut(); navigate("/register"); }}
              className="text-muted hover:text-text cursor-pointer"
            >
              Use a different email
            </button>
          </div>
          <p className="mt-8 text-center text-xs text-subtle">Can't find it? Check your spam or promotions folder.</p>
        </div>
      </main>
    </div>
  );
}
