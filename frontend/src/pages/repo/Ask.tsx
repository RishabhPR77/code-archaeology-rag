import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, ChevronDown, GitPullRequest, MessageSquareText, Plus, Sparkles, Square, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ProviderMark } from "../../components/brand";
import { Markdown } from "../../components/Markdown";
import { Button, Card, ConfirmDialog, ErrorNotice, Segmented, Skeleton } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { useSession } from "../../lib/auth";
import type { AskMode, Chat, QueryResult, Repo } from "../../lib/types";
import { cn, formatDate, relativeTime, shortSha } from "../../lib/utils";

const SUGGESTIONS = [
  "What are the most significant changes made recently?",
  "Which bugs were fixed, and what caused them?",
  "Were there any major refactors? Why were they done?",
  "Summarize what each contributor worked on.",
  "Which parts of the codebase are the most fragile?",
  "What new features were added and why?",
];

// The answer being written: text so far, and what the search found
interface Draft { text: string; searchQuery: string | null; found: boolean }

// The user pressed Stop
const isAbort = (e: unknown) => e instanceof DOMException && e.name === "AbortError";

const MODES: { value: AskMode; label: string }[] = [
  { value: "detailed", label: "Detailed" },
  { value: "summary", label: "Summary" },
  { value: "bullets", label: "Bullets" },
];

function Sources({ result, repoUrl }: { result: QueryResult; repoUrl: string }) {
  const [open, setOpen] = useState(false);
  if (!result.sources.length) return null;
  return (
    <div className="mt-4 border-t border-border pt-3">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
              className="flex items-center gap-1.5 text-xs font-medium text-muted hover:text-text cursor-pointer">
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
        {result.sources.length} source commits
      </button>
      {open && (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {result.sources.map((s) => (
            <li key={s.sha}>
              <a href={`${repoUrl}/commit/${s.sha}`} target="_blank" rel="noopener noreferrer"
                 className="block rounded-lg border border-border bg-surface-2/60 p-3 transition-colors hover:border-border-strong">
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="font-mono font-semibold text-accent">{shortSha(s.sha)}</span>
                  <span className="truncate text-muted">{s.author}</span>
                  <span className="ml-auto shrink-0 text-subtle">{formatDate(s.timestamp)}</span>
                </div>
                <p className="mt-1.5 line-clamp-2 text-[12px] leading-snug">{s.message}</p>
                <div className="mt-2 flex items-center gap-2 text-[11px] text-subtle">
                  {s.pr_number && <span className="inline-flex items-center gap-1"><GitPullRequest className="size-3" />#{s.pr_number}</span>}
                  <span className="truncate font-mono">{s.files.slice(0, 2).join(", ")}{s.files.length > 2 && ` +${s.files.length - 2}`}</span>
                  <span className="ml-auto shrink-0 font-mono">{s.score.toFixed(2)}</span>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Exchange({ q, repoUrl }: { q: QueryResult; repoUrl: string }) {
  return (
    <div className="space-y-3 animate-fade-up">
      <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[14px] text-accent-fg">
        {q.question}
      </div>
      {q.search_query && (
        // A follow-up was rewritten to stand on its own; showing it explains which commits came back
        <p className="ml-auto w-fit max-w-[85%] text-right text-xs text-subtle">
          Searched for: <span className="text-muted">{q.search_query}</span>
        </p>
      )}
      <Card className="p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-subtle">
          <ProviderMark id={q.provider} className="size-5 text-[8px]" />
          <span className="font-mono">{q.model}</span>
          <span>·</span>
          <span className="capitalize">{q.mode}</span>
          <span className="ml-auto">{relativeTime(q.created_at)}</span>
        </div>
        <Markdown repoUrl={repoUrl}>{q.answer}</Markdown>
        <Sources result={q} repoUrl={repoUrl} />
      </Card>
    </div>
  );
}

function ChatList({ chats, active, onSelect, onNew, onDelete }: {
  chats: Chat[]; active: number | null; onSelect: (id: number) => void; onNew: () => void;
  onDelete: (chat: Chat) => void;
}) {
  return (
    <nav aria-label="Chats" className="space-y-4">
      <Button variant="secondary" className="w-full justify-start" onClick={onNew} aria-pressed={active === null}>
        <Plus className="size-4" /> New chat
      </Button>
      <div>
        <p className="px-2.5 text-[11px] font-semibold uppercase tracking-wider text-subtle">Chats</p>
        {chats.length === 0 ? (
          <p className="mt-2 px-2.5 text-[13px] text-subtle">Your chats will appear here.</p>
        ) : (
          <ul className="mt-2 space-y-0.5">
            {chats.map((c) => (
              <li key={c.id} className="group relative">
                <button onClick={() => onSelect(c.id)} aria-current={active === c.id ? "true" : undefined}
                        className={cn("block w-full rounded-lg py-2 pr-9 pl-2.5 text-left transition-colors cursor-pointer",
                          active === c.id ? "bg-accent-soft text-text" : "text-muted hover:bg-surface-2 hover:text-text")}>
                  <span className="block truncate text-[13px] font-medium">{c.title}</span>
                  <span className="block text-[11px] text-subtle">
                    {relativeTime(c.updated_at)} · {c.questions} {c.questions === 1 ? "question" : "questions"}
                  </span>
                </button>
                <button onClick={() => onDelete(c)} aria-label={`Delete chat: ${c.title}`} title="Delete chat"
                        className="absolute top-2 right-1.5 rounded-md p-1.5 text-subtle opacity-0 transition-opacity hover:text-danger group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100 cursor-pointer">
                  <Trash2 className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}

export function Ask({ repo }: { repo: Repo }) {
  const { user } = useSession();
  const qc = useQueryClient();
  // The open chat lives in the URL, so a reload or a shared link keeps it
  const [params, setParams] = useSearchParams();
  const chatId = Number(params.get("chat")) || null;
  const chatsKey = ["repo-data", repo.id, "chats"];
  const messagesKey = (id: number) => ["repo-data", repo.id, "chat", id];
  const chats = useQuery({ queryKey: chatsKey, queryFn: () => api.chats(repo.id) });
  const messages = useQuery({
    queryKey: messagesKey(chatId ?? 0),
    queryFn: () => api.chat(repo.id, chatId!),
    enabled: chatId !== null,
  });
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<AskMode>("detailed");
  const [onlyPr, setOnlyPr] = useState(false);
  const [toDelete, setToDelete] = useState<Chat | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const stopper = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const hasModel = !!(user.active_provider && user.active_model);

  const select = (id: number | null) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (id === null) next.delete("chat");
      else next.set("chat", String(id));
      return next;
    }, { replace: true });
  };

  const ask = useMutation({
    mutationFn: async ({ q, chat, mode }: { q: string; chat: number | null; mode: AskMode }) => {
      const controller = new AbortController();
      stopper.current = controller;
      let text = "";
      let timer: number | undefined;
      // Re-rendering the Markdown for every small piece is wasteful; show new text at most every 50 ms
      const show = () => { timer = undefined; setDraft((d) => d && { ...d, text }); };
      setDraft({ text: "", searchQuery: null, found: false });
      try {
        return await api.ask(repo.id, q, mode, onlyPr, chat, {
          onSources: ({ search_query }) => setDraft((d) => d && { ...d, searchQuery: search_query, found: true }),
          onText: (piece) => { text += piece; timer ??= window.setTimeout(show, 50); },
        }, controller.signal);
      } finally {
        window.clearTimeout(timer);
        show();
        stopper.current = null;
      }
    },
    onSuccess: (result, { chat }) => {
      const id = result.conversation_id!;
      qc.setQueryData<QueryResult[]>(messagesKey(id), (old) => [...(old ?? []), result]);
      qc.invalidateQueries({ queryKey: chatsKey });
      setDraft(null);
      setQuestion("");
      // A first question opens its new chat, unless the user has moved to another one meanwhile
      if (chat === null && chatId === null) select(id);
    },
    // A stopped answer simply disappears; any other failure keeps the text so far next to the error
    onError: (error) => { if (isAbort(error)) setDraft(null); },
  });
  const remove = useMutation({
    mutationFn: (chat: Chat) => api.deleteChat(repo.id, chat.id),
    onSuccess: (_, chat) => {
      qc.removeQueries({ queryKey: messagesKey(chat.id) });
      qc.invalidateQueries({ queryKey: chatsKey });
      if (chat.id === chatId) select(null);
      setToDelete(null);
      toast.success("Chat deleted");
    },
  });

  // A chat link that no longer exists falls back to a new chat
  const missing = messages.error instanceof ApiError && messages.error.status === 404;
  useEffect(() => {
    if (missing) setParams((prev) => { const next = new URLSearchParams(prev); next.delete("chat"); return next; }, { replace: true });
  }, [missing, setParams]);

  const items = chatId !== null ? messages.data ?? [] : [];
  const askedHere = ask.variables?.chat === chatId;
  const pendingHere = ask.isPending && askedHere;
  const askError = ask.error && !isAbort(ask.error) ? ask.error : null;
  const showDraft = draft !== null && askedHere && (ask.isPending || askError !== null);

  useEffect(() => {
    if (items.length || pendingHere) bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items.length, pendingHere, chatId]);

  // Follow the answer as it grows, unless the user has scrolled up to read something else
  const draftText = draft?.text ?? "";
  useEffect(() => {
    const marker = bottom.current;
    if (draftText && marker && marker.getBoundingClientRect().top - window.innerHeight < 240) {
      marker.scrollIntoView({ block: "end" });
    }
  }, [draftText]);

  const submit = (q = question) => {
    if (q.trim().length >= 3 && !ask.isPending) ask.mutate({ q: q.trim(), chat: chatId, mode });
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };
  const newChat = () => { select(null); setQuestion(""); };
  const chatList = chats.data ?? [];

  return (
    <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="hidden lg:sticky lg:top-4 lg:block lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto">
        <ChatList chats={chatList} active={chatId} onSelect={select} onNew={newChat} onDelete={setToDelete} />
      </aside>

      <div className="mx-auto w-full max-w-3xl min-w-0">
        <div className="mb-5 flex items-center gap-2 lg:hidden">
          <label htmlFor="chat-picker" className="sr-only">Chat</label>
          <select id="chat-picker" value={chatId ?? ""} onChange={(e) => select(e.target.value ? Number(e.target.value) : null)}
                  className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-surface px-2.5 text-[13px] text-text">
            <option value="">New chat</option>
            {chatList.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          <Button variant="secondary" size="sm" className="h-9" onClick={newChat}><Plus className="size-4" /> New</Button>
          {chatId !== null && (
            <Button variant="ghost" size="icon" aria-label="Delete this chat"
                    onClick={() => setToDelete(chatList.find((c) => c.id === chatId) ?? null)}>
              <Trash2 className="size-4" />
            </Button>
          )}
        </div>

        {!hasModel && (
          <div className="mb-5 rounded-lg border border-warning/25 bg-warning-soft px-4 py-3 text-[13px] text-warning">
            Connect a model provider to ask questions. <Link to="/app/settings" className="font-medium underline">Open settings</Link>
          </div>
        )}

        {chatId !== null && messages.isPending && <Skeleton className="h-40 rounded-xl" />}
        {messages.error && !missing && <ErrorNotice error={messages.error} />}

        {chatId === null && !pendingHere && (
          <div className="py-6 text-center">
            <div className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-soft text-accent"><Sparkles className="size-5" /></div>
            <h2 className="mt-4 text-base font-semibold">Ask about {repo.full_name}</h2>
            <p className="mt-1 text-[13px] text-muted">Answers come only from this repository's commits, PRs and reviews, with citations.</p>
            <div className="mt-6 grid gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => submit(s)} disabled={!hasModel || ask.isPending}
                        className="rounded-xl border border-border bg-surface p-3 text-left text-[13px] text-muted transition-colors hover:border-border-strong hover:text-text disabled:opacity-50 cursor-pointer">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-8">
          {items.map((q) => <Exchange key={q.id} q={q} repoUrl={repo.url} />)}
          {showDraft && draft && (
            <div className="space-y-3">
              <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[14px] text-accent-fg">{ask.variables?.q}</div>
              {draft.searchQuery && (
                <p className="ml-auto w-fit max-w-[85%] text-right text-xs text-subtle">
                  Searched for: <span className="text-muted">{draft.searchQuery}</span>
                </p>
              )}
              {draft.text ? (
                <Card className="p-5">
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-subtle">
                    {user.active_provider && <ProviderMark id={user.active_provider} className="size-5 text-[8px]" />}
                    <span className="font-mono">{user.active_model}</span>
                    <span>·</span>
                    <span className="capitalize">{ask.variables?.mode}</span>
                    {pendingHere && (
                      <span className="ml-auto inline-flex items-center gap-1.5 text-accent">
                        <span className="size-1.5 animate-pulse rounded-full bg-accent" /> Writing…
                      </span>
                    )}
                  </div>
                  <Markdown repoUrl={repo.url}>{draft.text}</Markdown>
                  {!pendingHere && <p className="mt-3 text-xs text-subtle">This answer stopped early, so it wasn't saved.</p>}
                </Card>
              ) : pendingHere && (
                <Card className="p-5">
                  <div className="flex items-center gap-2 text-xs text-muted">
                    <span className="flex gap-1">
                      {[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-bounce rounded-full bg-accent" style={{ animationDelay: `${i * 120}ms` }} />)}
                    </span>
                    {draft.found
                      ? <>Found the relevant commits. Waiting for <span className="font-mono">{user.active_model}</span>…</>
                      : "Searching this repository's history…"}
                  </div>
                  <div className="mt-4 space-y-2"><Skeleton className="h-3 w-11/12" /><Skeleton className="h-3 w-9/12" /><Skeleton className="h-3 w-10/12" /></div>
                </Card>
              )}
            </div>
          )}
        </div>

        {askError && askedHere && <ErrorNotice error={askError} className="mt-4" />}
        <div ref={bottom} />

        <div className="sticky bottom-0 mt-8 bg-gradient-to-t from-bg via-bg to-transparent pt-6 pb-4">
          <Card className="p-2 focus-within:border-accent">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={onKey}
              rows={2}
              maxLength={2000}
              disabled={!hasModel}
              placeholder={!hasModel ? "Connect a model provider first"
                : chatId === null ? "Why was the auth module refactored?" : "Ask another question in this chat"}
              aria-label="Your question"
              className="block w-full resize-none bg-transparent px-2 py-1.5 text-[14px] outline-none placeholder:text-subtle disabled:opacity-60"
            />
            <div className="flex flex-wrap items-center gap-2 px-1 pt-1">
              <Segmented size="sm" value={mode} onChange={setMode} options={MODES} />
              <label className="flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-muted hover:text-text">
                <input type="checkbox" checked={onlyPr} onChange={(e) => setOnlyPr(e.target.checked)} className="accent-[var(--accent)]" />
                Only commits with PRs
              </label>
              <div className="flex-1" />
              {ask.isPending ? (
                <Button size="icon" variant="secondary" className="size-8" onClick={() => stopper.current?.abort()}
                        aria-label="Stop the answer" title="Stop">
                  <Square className="size-3 fill-current" />
                </Button>
              ) : (
                <Button size="icon" className="size-8" onClick={() => submit()}
                        disabled={!hasModel || question.trim().length < 3} aria-label="Ask">
                  <ArrowUp className="size-4" />
                </Button>
              )}
            </div>
          </Card>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-[11px] text-subtle">
            <MessageSquareText className="size-3" />
            {chatId === null ? "Enter to send · Shift+Enter for a new line · uses your own API key"
              : "Follow-ups use this chat's last 3 questions and answers · uses your own API key"}
          </p>
        </div>
      </div>

      <ConfirmDialog open={toDelete !== null} onClose={() => setToDelete(null)}
                     onConfirm={() => toDelete && remove.mutate(toDelete)} loading={remove.isPending}
                     confirmLabel="Delete chat" title="Delete this chat?"
                     description={toDelete ? `“${toDelete.title}” and its answers are removed.` : ""} />
    </div>
  );
}
