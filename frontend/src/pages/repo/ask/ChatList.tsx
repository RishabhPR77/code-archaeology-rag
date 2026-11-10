import type { Chat } from "../../../lib/types";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "../../../components/ui";
import { cn, relativeTime } from "../../../lib/utils";

export function ChatList({ chats, active, onSelect, onNew, onDelete, onDeleteAll, readOnly }: {
  chats: Chat[]; active: number | null; onSelect: (id: number) => void; onNew: () => void;
  onDelete: (chat: Chat) => void; onDeleteAll: () => void; readOnly: boolean;
}) {
  return (
    <nav aria-label="Chats" className="space-y-4">
      {!readOnly && (
        <Button variant="secondary" className="w-full justify-start" onClick={onNew} aria-pressed={active === null}>
          <Plus className="size-4" /> New chat
        </Button>
      )}
      <div>
        <div className="flex items-center justify-between px-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-subtle">{readOnly ? "Saved chats" : "Chats"}</p>
          {!readOnly && chats.length > 1 && (
            <button onClick={onDeleteAll} className="text-[11px] text-subtle hover:text-danger cursor-pointer">Delete all</button>
          )}
        </div>
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
                {!readOnly && (
                  <button onClick={() => onDelete(c)} aria-label={`Delete chat: ${c.title}`} title="Delete chat"
                          className="absolute top-2 right-1.5 rounded-md p-1.5 text-subtle opacity-0 transition-opacity hover:text-danger group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100 cursor-pointer">
                    <Trash2 className="size-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}
