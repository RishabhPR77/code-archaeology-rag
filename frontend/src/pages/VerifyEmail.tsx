import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { Logo, ThemeToggle } from "../components/brand";
import { Button, ErrorNotice, Input } from "../components/ui";
import { api } from "../lib/api";
import { meKey, useSession, useSignOut } from "../lib/auth";

const RESEND_SECONDS = 60;

export default function VerifyEmail() {
  const { user } = useSession();
  const [code, setCode] = useState("");
  // The server knows when the last code went out, so a reload doesn't restart the wait
  const [cooldown, setCooldown] = useState(user.code_resend_in);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const signOut = useSignOut();

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const verify = useMutation({
    mutationFn: () => api.verifyEmail(code),
    onSuccess: (me) => {
      qc.setQueryData(meKey, me);
      toast.success("Email confirmed", { description: "Welcome to Code Archaeologist." });
      navigate("/app", { replace: true });
    },
  });
  const resend = useMutation({
    mutationFn: api.resendCode,
    onSuccess: () => {
      setCooldown(RESEND_SECONDS);
      setCode("");
      verify.reset();
      toast.success("New code sent", { description: `Check ${user.email}` });
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (code.length === 6) verify.mutate();
  };

  return (
    <div className="relative flex min-h-full flex-col">
      <div className="grid-bg absolute inset-0 -z-10 opacity-50" aria-hidden />
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
            We sent a 6-digit code to <span className="font-medium text-text">{user.email}</span>.
            It expires in 10 minutes.
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
              onClick={async () => { await signOut(); navigate("/register"); }}
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
