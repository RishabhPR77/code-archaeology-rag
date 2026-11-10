import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { Button, Card, CardHeader, Dialog, ErrorNotice, Input, Label } from "../../components/ui";
import { api } from "../../lib/api";
import { meKey, useSession } from "../../lib/auth";

export function DeleteAccountCard() {
  const { user } = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [code, setCode] = useState("");
  const remove = useMutation({
    mutationFn: () => api.deleteAccount(typed, user.two_factor_enabled ? code : undefined),
    onSuccess: () => {
      qc.clear();
      qc.setQueryData(meKey, null);
      toast.success("Your account was deleted");
      navigate("/", { replace: true });
    },
  });
  const ready = typed.trim().toLowerCase() === user.email.toLowerCase() && (!user.two_factor_enabled || code.length >= 6);
  const close = () => { setOpen(false); setTyped(""); setCode(""); remove.reset(); };

  return (
    <Card className="border-danger/30">
      <CardHeader title="Delete account"
                  description="Removes your account and everything in it: repositories, chats, API keys and history. This can't be undone." />
      <div className="border-t border-border px-5 py-4">
        <Button size="sm" variant="danger" onClick={() => setOpen(true)}><Trash2 className="size-3.5" /> Delete my account</Button>
      </div>
      <Dialog open={open} onClose={close} title="Delete your account?"
              description="Everything is deleted straight away, including your repositories' search data. It can't be undone.">
        <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); if (ready) remove.mutate(); }}>
          <div>
            <Label htmlFor="confirm-email">Type <span className="font-mono">{user.email}</span> to confirm</Label>
            <Input id="confirm-email" data-autofocus value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
          </div>
          {user.two_factor_enabled && (
            <div>
              <Label htmlFor="delete-code">Code from your authenticator app</Label>
              <Input id="delete-code" value={code} inputMode="numeric" autoComplete="one-time-code"
                     onChange={(e) => setCode(e.target.value.slice(0, 12))} />
            </div>
          )}
          {remove.error && <ErrorNotice error={remove.error} />}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={close}>Cancel</Button>
            <Button type="submit" variant="danger" loading={remove.isPending} disabled={!ready}>Delete everything</Button>
          </div>
        </form>
      </Dialog>
    </Card>
  );
}
