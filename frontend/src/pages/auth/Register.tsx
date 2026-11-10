import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { Button, ErrorNotice, Input, Label } from "../../components/ui";
import { api } from "../../lib/api";
import { AuthShell, NewPasswordFields, OAuthButtons, passwordsReady, pendingEmail, useAuthSuccess } from "./shared";

export function Register() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const navigate = useNavigate();
  const onSignedIn = useAuthSuccess();
  const register = useMutation({
    mutationFn: () => api.register(email, password, name),
    onSuccess: (res) => {
      if ("user" in res) return onSignedIn(res);       // no email codes on this server: signed in already
      // A code was emailed. The reply is the same whether or not the address already had an account
      pendingEmail.set(res.email);
      navigate("/verify-email", { state: { email: res.email, resendIn: res.resend_in } });
    },
  });

  const submit = (e: FormEvent) => { e.preventDefault(); if (passwordsReady(password, confirm)) register.mutate(); };

  return (
    <AuthShell title="Create your account" subtitle="Bring your own model key. Start digging in minutes."
               footer={<>Already have an account? <Link to="/login" className="font-medium text-accent hover:underline">Sign in</Link></>}>
      <OAuthButtons />
      <form onSubmit={submit} className="space-y-4">
        <div>
          <Label htmlFor="name">Name</Label>
          <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" />
        </div>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required autoComplete="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </div>
        <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
        {register.error && <ErrorNotice error={register.error} />}
        <Button type="submit" size="lg" className="w-full" loading={register.isPending}
                disabled={!passwordsReady(password, confirm)}>
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}
