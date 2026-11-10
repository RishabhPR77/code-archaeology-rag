import { useMutation } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Button, ErrorNotice, Input } from "../../components/ui";
import { api } from "../../lib/api";
import { AuthShell, useAuthSuccess } from "./shared";

/** The second step of signing in: a code from the authenticator app, or a recovery code. */
export function TwoFactorStep({ onCancel }: { onCancel?: () => void }) {
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const onSuccess = useAuthSuccess();
  const verify = useMutation({ mutationFn: () => api.twoFactor.verify(code), onSuccess });
  const ready = recovery ? code.replace(/[\s-]/g, "").length === 8 : code.length === 6;

  const submit = (e: FormEvent) => { e.preventDefault(); if (ready) verify.mutate(); };

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="flex items-start gap-3 rounded-xl border border-border bg-surface-2/50 p-4 text-[13px] text-muted">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" />
        {recovery
          ? "Enter one of the recovery codes you saved when you turned on two-step sign-in. Each works once."
          : "Open your authenticator app and enter the 6-digit code for Code Archaeologist."}
      </div>
      <Input
        value={code}
        onChange={(e) => setCode(recovery ? e.target.value.slice(0, 12) : e.target.value.replace(/\D/g, "").slice(0, 6))}
        inputMode={recovery ? "text" : "numeric"}
        autoComplete="one-time-code"
        autoFocus
        placeholder={recovery ? "xxxx-xxxx" : "000000"}
        aria-label={recovery ? "Recovery code" : "6-digit code"}
        className="h-14 text-center font-mono text-2xl tracking-[0.3em]"
      />
      {verify.error && <ErrorNotice error={verify.error} />}
      <Button type="submit" size="lg" className="w-full" loading={verify.isPending} disabled={!ready}>Verify</Button>
      <div className="flex items-center justify-between text-[13px]">
        <button type="button" className="font-medium text-accent hover:underline cursor-pointer"
                onClick={() => { setRecovery((r) => !r); setCode(""); verify.reset(); }}>
          {recovery ? "Use the authenticator app" : "Use a recovery code"}
        </button>
        {onCancel && <button type="button" onClick={onCancel} className="text-muted hover:text-text cursor-pointer">Back</button>}
      </div>
    </form>
  );
}

/** Where Google and GitHub sign-ins land when the account has two-step sign-in on. */
export function TwoFactorPage() {
  return (
    <AuthShell title="Two-step sign-in" subtitle="One more step to keep your account safe."
               footer={<Link to="/login" className="font-medium text-accent hover:underline">Start over</Link>}>
      <TwoFactorStep />
    </AuthShell>
  );
}
