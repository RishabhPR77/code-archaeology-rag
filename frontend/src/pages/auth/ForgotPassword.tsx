import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { Button, ErrorNotice, Input, Label } from "../../components/ui";
import { api } from "../../lib/api";
import { AuthShell, NewPasswordFields, passwordsReady } from "./shared";

/** Email a reset code, then choose a new password with it. Step one never says whether the address
 *  has an account: that would let anyone check which emails are registered. */
export function ForgotPassword() {
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState((location.state as { email?: string } | null)?.email ?? "");
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const send = useMutation({ mutationFn: () => api.forgotPassword(email), onSuccess: () => setSent(true) });
  const reset = useMutation({
    mutationFn: () => api.resetPassword(email, code, password),
    onSuccess: () => navigate("/login", {
      replace: true, state: { notice: "Password changed. Sign in with your new password." },
    }),
  });

  if (!sent) {
    return (
      <AuthShell title="Reset your password" subtitle="We'll email you a 6-digit code."
                 footer={<Link to="/login" className="font-medium text-accent hover:underline">Back to sign in</Link>}>
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); send.mutate(); }} className="space-y-4">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" required autoComplete="email" autoFocus value={email}
                   onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
          </div>
          {send.error && <ErrorNotice error={send.error} />}
          <Button type="submit" size="lg" className="w-full" loading={send.isPending}>Send code</Button>
        </form>
      </AuthShell>
    );
  }

  const ready = code.length === 6 && passwordsReady(password, confirm);
  return (
    <AuthShell title="Choose a new password"
               subtitle={<>If <span className="font-medium text-text">{email}</span> has an account, a code is on its way. It expires in 10 minutes.</>}
               footer={<button onClick={() => { setSent(false); setCode(""); reset.reset(); }}
                               className="font-medium text-accent hover:underline cursor-pointer">Use a different email</button>}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); if (ready) reset.mutate(); }} className="space-y-4">
        <div>
          <Label htmlFor="code">Code from the email</Label>
          <Input id="code" value={code} inputMode="numeric" autoComplete="one-time-code" autoFocus placeholder="000000"
                 onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                 className="h-12 text-center font-mono text-xl tracking-[0.4em]" />
        </div>
        <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm}
                           label="New password" />
        {reset.error && <ErrorNotice error={reset.error} />}
        <Button type="submit" size="lg" className="w-full" loading={reset.isPending} disabled={!ready}>
          Change password
        </Button>
        <p className="text-center text-xs text-subtle">Changing it signs you out on every other device.</p>
      </form>
    </AuthShell>
  );
}
