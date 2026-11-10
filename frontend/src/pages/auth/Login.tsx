import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { Button, ErrorNotice, Input, Label } from "../../components/ui";
import { api } from "../../lib/api";
import { AuthShell, OAUTH_ERRORS, OAuthButtons, PasswordInput, useAuthSuccess } from "./shared";
import { TwoFactorStep } from "./TwoFactor";

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [params] = useSearchParams();
  const location = useLocation();
  const onSuccess = useAuthSuccess();
  const login = useMutation({
    mutationFn: () => api.login(email, password),
    onSuccess: (res) => ("two_factor_required" in res ? setNeedsCode(true) : onSuccess(res)),
  });
  const oauthError = OAUTH_ERRORS[params.get("error") ?? ""];
  const notice = (location.state as { notice?: string } | null)?.notice;

  const submit = (e: FormEvent) => { e.preventDefault(); login.mutate(); };

  if (needsCode) {
    return (
      <AuthShell title="Two-step sign-in" subtitle="Your password was right. One more step.">
        <TwoFactorStep onCancel={() => { setNeedsCode(false); setPassword(""); }} />
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your workspace."
               footer={<>New here? <Link to="/register" className="font-medium text-accent hover:underline">Create an account</Link></>}>
      {notice && <p className="mb-5 rounded-lg bg-accent-soft px-3 py-2.5 text-[13px] text-accent">{notice}</p>}
      {oauthError && <ErrorNotice error={new Error(oauthError)} className="mb-5" />}
      <OAuthButtons />
      <form onSubmit={submit} className="space-y-4">
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required autoComplete="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label htmlFor="password" className="text-[13px] font-medium">Password</label>
            <Link to="/forgot-password" state={{ email }} className="text-xs font-medium text-accent hover:underline">
              Forgot password?
            </Link>
          </div>
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="current-password" />
        </div>
        {login.error && (
          <div>
            <ErrorNotice error={login.error} />
            <p className="mt-2 text-xs text-muted">Signed up with Google or GitHub? Use those buttons instead.</p>
          </div>
        )}
        <Button type="submit" size="lg" className="w-full" loading={login.isPending}>Sign in</Button>
      </form>
    </AuthShell>
  );
}
