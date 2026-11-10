import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, ShieldCheck } from "lucide-react";

import { Card, CardHeader, ErrorNotice, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate, relativeTime } from "../../lib/utils";
import { activityKey } from "./SecurityCard";

// Events worth a second look if they weren't you
const WARN = new Set(["sign_in_failed", "two_factor_failed", "two_factor_disabled", "recovery_code_used", "password_reset"]);

export function ActivityCard() {
  const events = useQuery({ queryKey: activityKey, queryFn: api.activity });
  return (
    <Card>
      <CardHeader title="Security activity"
                  description="Recent sign-ins and changes to your account. Something you don't recognise? Change your password and sign out everywhere." />
      {events.error && <div className="p-5"><ErrorNotice error={events.error} /></div>}
      {events.isPending ? (
        <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 rounded-lg" />)}</div>
      ) : events.data?.length ? (
        <ul className="max-h-96 divide-y divide-border overflow-y-auto border-t border-border text-[13px]">
          {events.data.map((e, i) => (
            <li key={i} className="flex items-start gap-3 px-5 py-3">
              {WARN.has(e.kind)
                ? <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warning" />
                : <ShieldCheck className="mt-0.5 size-4 shrink-0 text-subtle" />}
              <div className="min-w-0 flex-1">
                <p><span className="font-medium">{e.label}</span>{e.detail && <span className="text-muted"> {e.detail}</span>}</p>
                <p className="mt-0.5 text-xs text-subtle">
                  {[e.device, e.ip && `network ${e.ip}`].filter(Boolean).join(" · ") || "No device details"}
                </p>
              </div>
              <time dateTime={e.created_at} title={formatDate(e.created_at, { dateStyle: "medium", timeStyle: "short" })}
                    className="shrink-0 text-xs text-subtle">{relativeTime(e.created_at)}</time>
            </li>
          ))}
        </ul>
      ) : <p className="border-t border-border px-5 py-4 text-[13px] text-muted">Nothing yet.</p>}
    </Card>
  );
}
