import {
  AlertTriangle, Check, ChevronDown, ChevronRight, Eye, LayoutGrid, LogOut, Plus, Settings, UserRound,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useMatch, useNavigate } from "react-router";

import { LogoMark, ProviderMark, ThemeToggle } from "../components/brand";
import { NewRepoDialog } from "../components/NewRepoDialog";
import { RepoAvatar, StatusDot } from "../components/RepoAvatar";
import { Button } from "../components/ui";
import { useSession, useSignOut } from "../lib/auth";
import { useRepos } from "../lib/queries";
import { cn } from "../lib/utils";

/** Closes a popover on a click outside it or on Escape. */
function useDismiss(open: boolean, close: () => void) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) close(); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open, close]);
  return box;
}

const MENU = "absolute z-50 mt-2 rounded-xl border border-border bg-surface p-1 shadow-card animate-fade-up";
const ITEM = "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] text-muted hover:bg-surface-2 hover:text-text cursor-pointer";

/** In a repository, its name in the top bar switches to another one. */
function RepoSwitcher({ repoId, onNewRepo }: { repoId: string; onNewRepo: () => void }) {
  const { user } = useSession();
  const { data: repos } = useRepos();
  const [open, setOpen] = useState(false);
  const box = useDismiss(open, () => setOpen(false));
  const current = repos?.find((r) => r.id === repoId);
  if (!current) return null;
  const [owner, name] = current.full_name.split("/");

  return (
    <div ref={box} className="relative min-w-0">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}
              className={cn("flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-surface-2 cursor-pointer",
                open && "bg-surface-2")}>
        <RepoAvatar fullName={current.full_name} className="size-6 rounded-md" />
        <span className="min-w-0 truncate text-[13px]">
          <span className="hidden text-subtle sm:inline">{owner} / </span>
          <span className="font-semibold">{name}</span>
        </span>
        <ChevronDown className="size-3.5 shrink-0 text-subtle" />
      </button>
      {open && (
        <div role="menu" className={cn(MENU, "left-0 w-72")}>
          <p className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">Switch repository</p>
          <div className="max-h-72 overflow-y-auto">
            {repos?.map((r) => (
              <Link key={r.id} to={`/app/repos/${r.id}`} role="menuitem" onClick={() => setOpen(false)}
                    className={cn(ITEM, r.id === repoId && "bg-accent-soft text-text")}>
                <span className="relative shrink-0">
                  <RepoAvatar fullName={r.full_name} className="size-6 rounded-md" />
                  <StatusDot repo={r} className="absolute -right-0.5 -bottom-0.5 size-1.5" />
                </span>
                <span className="min-w-0 flex-1 truncate">{r.full_name}</span>
                {r.id === repoId && <Check className="size-3.5 text-accent" />}
              </Link>
            ))}
          </div>
          <div className="mt-1 border-t border-border pt-1">
            <Link to="/app" role="menuitem" onClick={() => setOpen(false)} className={ITEM}>
              <LayoutGrid className="size-4" /> All repositories
            </Link>
            {!user.is_demo && (
              <button role="menuitem" onClick={() => { setOpen(false); onNewRepo(); }} className={ITEM}>
                <Plus className="size-4" /> New repository
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function AccountMenu() {
  const { user } = useSession();
  const signOut = useSignOut();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useDismiss(open, () => setOpen(false));

  const name = user.is_demo ? "Demo" : user.name || user.email;
  const detail = user.is_demo ? "Read-only" : user.email;
  const leave = async () => {
    setOpen(false);
    await signOut();
    navigate(user.is_demo ? "/" : "/login");
  };

  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} aria-label="Account"
              className={cn("grid size-9 place-items-center rounded-full ring-offset-2 ring-offset-bg transition-shadow hover:ring-2 hover:ring-border-strong cursor-pointer",
                open && "ring-2 ring-accent/50")}>
        {user.is_demo ? (
          <span className="grid size-8 place-items-center rounded-full bg-accent-soft text-accent"><Eye className="size-4" /></span>
        ) : user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="size-8 rounded-full" />
        ) : (
          <span className="grid size-8 place-items-center rounded-full bg-accent-soft text-[13px] font-semibold text-accent">
            {name[0].toUpperCase()}
          </span>
        )}
      </button>
      {open && (
        <div role="menu" className={cn(MENU, "right-0 w-60")}>
          <div className="border-b border-border px-2.5 pt-1.5 pb-2">
            <p className="truncate text-[13px] font-medium">{name}</p>
            <p className="truncate text-[11px] text-subtle">{detail}</p>
          </div>
          <div className="pt-1">
            {!user.is_demo && (
              <Link to="/app/profile" role="menuitem" onClick={() => setOpen(false)} className={ITEM}>
                <UserRound className="size-4" /> Profile
              </Link>
            )}
            <Link to="/app" role="menuitem" onClick={() => setOpen(false)} className={ITEM}>
              <LayoutGrid className="size-4" /> Repositories
            </Link>
            {!user.is_demo && (
              <Link to="/app/settings" role="menuitem" onClick={() => setOpen(false)} className={ITEM}>
                <Settings className="size-4" /> Settings
              </Link>
            )}
            <button role="menuitem" onClick={leave} className={ITEM}>
              <LogOut className="size-4" /> {user.is_demo ? "Leave the demo" : "Sign out"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ModelChip() {
  const { user } = useSession();
  if (!user.active_provider || !user.active_model) {
    return (
      <Link to="/app/settings" title="Connect a model"
            className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-soft px-2.5 py-1.5 text-[13px] font-medium text-warning">
        <AlertTriangle className="size-3.5" />
        <span className="hidden md:inline">Connect a model</span>
      </Link>
    );
  }
  return (
    <Link to="/app/settings" title={`Model: ${user.active_model}. Change it in Settings`}
          className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-surface px-1.5 py-1 text-[13px] transition-colors hover:border-border-strong md:px-2">
      <ProviderMark id={user.active_provider} className="size-6 text-[9px]" />
      <span className="hidden max-w-40 truncate font-mono text-xs text-muted md:inline">{user.active_model}</span>
      <ChevronRight className="hidden size-3.5 text-subtle md:block" />
    </Link>
  );
}

export function AppLayout({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const [newRepoOpen, setNewRepoOpen] = useState(false);
  const inRepo = useMatch({ path: "/app/repos/:repoId", end: false });
  const repoId = inRepo?.params.repoId;

  return (
    <div className="flex h-full flex-col">
      <header className="sticky top-0 z-30 shrink-0 border-b border-border bg-surface/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-3 sm:px-6">
          <Link to="/app" aria-label="All repositories" className="flex shrink-0 items-center gap-2.5 font-semibold tracking-tight">
            <LogoMark />
            <span className={cn("text-[15px]", repoId ? "hidden lg:inline" : "hidden sm:inline")}>Code Archaeologist</span>
          </Link>
          {repoId && (
            <>
              <span className="text-border-strong" aria-hidden>/</span>
              <RepoSwitcher repoId={repoId} onNewRepo={() => setNewRepoOpen(true)} />
            </>
          )}
          <div className="flex-1" />
          {user.is_demo ? (
            <>
              <ThemeToggle />
              <Link to="/register"><Button size="sm">Sign up free</Button></Link>
            </>
          ) : (
            <>
              <ModelChip />
              <ThemeToggle />
              <Button size="sm" onClick={() => setNewRepoOpen(true)} aria-label="New repository">
                <Plus className="size-4" /> <span className="hidden sm:inline">New repository</span>
              </Button>
            </>
          )}
          <AccountMenu />
        </div>
      </header>
      {user.is_demo && (
        <div className="shrink-0 border-b border-border bg-accent-soft">
          <div className="mx-auto flex max-w-6xl items-start gap-2 px-4 py-2 text-[13px] text-text sm:px-6">
            <Eye className="mt-0.5 size-4 shrink-0 text-accent" />
            <p>
              <span className="font-medium">This is a read-only demo.</span>{" "}
              <span className="hidden text-muted sm:inline">Browse a sample repository, its saved chats and Who broke it?.
              Sign up free to ask your own questions about your own repositories.</span>
            </p>
          </div>
        </div>
      )}
      <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>

      {!user.is_demo && <NewRepoDialog open={newRepoOpen} onClose={() => setNewRepoOpen(false)} />}
    </div>
  );
}
