import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, LogOut } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { Badge, Button, Card, CardHeader, Dialog, ErrorNotice, Input, Label } from "../../components/ui";
import { api } from "../../lib/api";
import { meKey, useSession, useSignOut } from "../../lib/auth";
import type { TwoFactorSetup } from "../../lib/types";
import { NewPasswordFields, PasswordInput, passwordsReady } from "../auth/shared";

export const activityKey = ["activity"] as const;

function CodeInput({ value, onChange, allowRecovery = false }: {
  value: string; onChange: (v: string) => void; allowRecovery?: boolean;
}) {
  return (
    <Input value={value} autoFocus data-autofocus autoComplete="one-time-code"
           inputMode={allowRecovery ? "text" : "numeric"} placeholder={allowRecovery ? "000000 or xxxx-xxxx" : "000000"}
           aria-label="Code from your authenticator app"
           onChange={(e) => onChange(allowRecovery ? e.target.value.slice(0, 12) : e.target.value.replace(/\D/g, "").slice(0, 6))}
           className="h-12 text-center font-mono text-xl tracking-[0.3em]" />
  );
}

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const text = `Code Archaeologist recovery codes\nEach code works once.\n\n${codes.join("\n")}\n`;
  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "code-archaeologist-recovery-codes.txt" });
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="space-y-4">
      <p className="text-[13px] text-muted">
        If you lose your phone, each of these signs you in once. Keep them somewhere safe, like a password manager.
        They won't be shown again.
      </p>
      <ul className="grid grid-cols-2 gap-2 rounded-xl border border-border bg-surface-2/50 p-4 font-mono text-[13px]">
        {codes.map((c) => <li key={c}>{c}</li>)}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary"
                onClick={() => navigator.clipboard.writeText(codes.join("\n")).then(() => toast.success("Copied"))}>
          <Copy className="size-3.5" /> Copy
        </Button>
        <Button size="sm" variant="secondary" onClick={download}><Download className="size-3.5" /> Download</Button>
        <div className="flex-1" />
        <Button size="sm" onClick={onDone}>I've saved them</Button>
      </div>
    </div>
  );
}

function TurnOnDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const start = useMutation({ mutationFn: api.twoFactor.setup, onSuccess: setSetup });
  const enable = useMutation({
    mutationFn: () => api.twoFactor.enable(code),
    onSuccess: (res) => { setCodes(res.codes); qc.invalidateQueries({ queryKey: meKey }); qc.invalidateQueries({ queryKey: activityKey }); },
  });
  const close = () => { setSetup(null); setCode(""); setCodes(null); start.reset(); enable.reset(); onClose(); };
  const { mutate: begin } = start;
  useEffect(() => { if (open) begin(); }, [open, begin]);   // a fresh secret each time the dialog opens

  return (
    <Dialog open={open} onClose={close} title={codes ? "Save your recovery codes" : "Turn on two-step sign-in"}
            description={codes ? undefined : "Use an authenticator app such as Google Authenticator, Microsoft Authenticator or 1Password."}>
      {codes ? <RecoveryCodes codes={codes} onDone={() => { close(); toast.success("Two-step sign-in is on"); }} /> : (
        <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); if (code.length === 6) enable.mutate(); }}>
          {start.error && <ErrorNotice error={start.error} />}
          {setup && (
            <>
              <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
                <img src={setup.qr_svg} alt="QR code to scan with your authenticator app"
                     className="size-40 shrink-0 rounded-lg border border-border bg-white p-1" />
                <ol className="list-decimal space-y-2 pl-5 text-[13px] text-muted">
                  <li>Scan the QR code with the app.</li>
                  <li>Can't scan? Enter this key instead:
                    <span className="mt-1 block break-all font-mono text-xs text-text">{setup.secret}</span>
                  </li>
                  <li>Type the 6-digit code the app shows.</li>
                </ol>
              </div>
              <CodeInput value={code} onChange={setCode} />
            </>
          )}
          {enable.error && <ErrorNotice error={enable.error} />}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={close}>Cancel</Button>
            <Button type="submit" loading={enable.isPending} disabled={code.length !== 6}>Turn on</Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

function CodeDialog({ open, onClose, title, description, action, confirmLabel, danger, onDone }: {
  open: boolean; onClose: () => void; title: string; description: string; confirmLabel: string; danger?: boolean;
  action: (code: string) => Promise<{ codes?: string[] } | unknown>; onDone: (result: unknown) => void;
}) {
  const [code, setCode] = useState("");
  const run = useMutation({ mutationFn: () => action(code), onSuccess: (r) => { setCode(""); onDone(r); } });
  const close = () => { setCode(""); run.reset(); onClose(); };
  return (
    <Dialog open={open} onClose={close} title={title} description={description}>
      <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); run.mutate(); }}>
        <CodeInput value={code} onChange={setCode} allowRecovery />
        {run.error && <ErrorNotice error={run.error} />}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={close}>Cancel</Button>
          <Button type="submit" variant={danger ? "danger" : "primary"} loading={run.isPending} disabled={code.length < 6}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function PasswordForm() {
  const { user } = useSession();
  const qc = useQueryClient();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [open, setOpen] = useState(false);
  const change = useMutation({
    mutationFn: () => api.changePassword(user.has_password ? current : null, password),
    onSuccess: (me) => {
      qc.setQueryData(meKey, me);
      qc.invalidateQueries({ queryKey: activityKey });
      setCurrent(""); setPassword(""); setConfirm(""); setOpen(false);
      toast.success(user.has_password ? "Password changed" : "Password added",
                    { description: "Other devices were signed out." });
    },
  });
  const ready = passwordsReady(password, confirm) && (!user.has_password || current.length > 0);

  return (
    <div className="px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[13px] font-medium">Password</p>
          <p className="mt-0.5 text-xs text-muted">
            {user.has_password ? "Changing it signs you out on every other device."
              : "You sign in with Google or GitHub. Add a password to sign in with your email too."}
          </p>
        </div>
        {!open && <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          {user.has_password ? "Change password" : "Add a password"}</Button>}
      </div>
      {open && (
        <form className="mt-4 max-w-sm space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); if (ready) change.mutate(); }}>
          {user.has_password && (
            <div>
              <Label htmlFor="current-password">Current password</Label>
              <PasswordInput id="current-password" value={current} onChange={setCurrent} autoComplete="current-password" />
            </div>
          )}
          <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm}
                             label="New password" />
          {change.error && <ErrorNotice error={change.error} />}
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={change.isPending} disabled={!ready}>Save password</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => { setOpen(false); change.reset(); }}>Cancel</Button>
          </div>
        </form>
      )}
    </div>
  );
}

export function SecurityCard() {
  const { user } = useSession();
  const qc = useQueryClient();
  const signOut = useSignOut();
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<"on" | "off" | "codes" | null>(null);
  const [newCodes, setNewCodes] = useState<string[] | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: meKey }); qc.invalidateQueries({ queryKey: activityKey }); };

  return (
    <Card>
      <CardHeader title="Security" description="How you sign in, and where you're signed in." />
      <div className="divide-y divide-border border-t border-border">
        <PasswordForm />

        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div>
            <p className="flex items-center gap-2 text-[13px] font-medium">
              Two-step sign-in {user.two_factor_enabled ? <Badge tone="success">On</Badge> : <Badge>Off</Badge>}
            </p>
            <p className="mt-0.5 text-xs text-muted">
              {user.two_factor_enabled
                ? `Signing in also asks for a code from your authenticator app. ${user.recovery_codes_left} recovery codes left.`
                : "Ask for a code from an authenticator app as well as your password, Google or GitHub."}
            </p>
          </div>
          {user.two_factor_enabled ? (
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setDialog("codes")}>New recovery codes</Button>
              <Button size="sm" variant="ghost" className="hover:text-danger" onClick={() => setDialog("off")}>Turn off</Button>
            </div>
          ) : <Button size="sm" onClick={() => setDialog("on")}>Turn on</Button>}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div>
            <p className="text-[13px] font-medium">Sessions</p>
            <p className="mt-0.5 text-xs text-muted">Lost a device, or signed in somewhere public? End every session at once.</p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={async () => { await signOut(); navigate("/login"); }}>
              <LogOut className="size-3.5" /> Sign out
            </Button>
            <Button size="sm" variant="ghost" onClick={async () => {
              await api.logoutEverywhere().catch(() => undefined);
              await signOut();
              toast.success("Signed out on every device");
              navigate("/login");
            }}>Sign out everywhere</Button>
          </div>
        </div>
      </div>

      <TurnOnDialog open={dialog === "on"} onClose={() => { setDialog(null); refresh(); }} />
      <CodeDialog open={dialog === "off"} onClose={() => setDialog(null)} danger confirmLabel="Turn off"
                  title="Turn off two-step sign-in?" description="Enter a code from your app, or a recovery code."
                  action={api.twoFactor.disable}
                  onDone={() => { setDialog(null); refresh(); toast.success("Two-step sign-in is off"); }} />
      <CodeDialog open={dialog === "codes"} onClose={() => setDialog(null)} confirmLabel="Create new codes"
                  title="New recovery codes" description="Your old recovery codes stop working. Enter a code from your app."
                  action={api.twoFactor.newRecoveryCodes}
                  onDone={(r) => { setDialog(null); setNewCodes((r as { codes: string[] }).codes); refresh(); }} />
      <Dialog open={newCodes !== null} onClose={() => setNewCodes(null)} title="Save your new recovery codes">
        {newCodes && <RecoveryCodes codes={newCodes} onDone={() => setNewCodes(null)} />}
      </Dialog>
    </Card>
  );
}
