import { ExternalLink } from "lucide-react";

// Hosts like Hugging Face Spaces show the app inside an iframe, where browsers
// won't send the SameSite session cookie — so sign-in only works in its own tab.
const framed = (() => {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
})();

export function FrameNotice() {
  if (!framed) return null;
  return (
    <div className="fixed bottom-4 left-1/2 z-50 flex w-max max-w-[calc(100%-2rem)] -translate-x-1/2 flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-xl bg-accent px-4 py-2 text-[13px] font-medium text-accent-fg shadow-2xl">
      <span>Signing in needs the app in its own tab.</span>
      <a href={window.location.href} target="_blank" rel="noopener noreferrer"
         className="inline-flex items-center gap-1 rounded-md bg-black/15 px-2.5 py-1 hover:bg-black/25">
        Open in a new tab <ExternalLink className="size-3.5" />
      </a>
    </div>
  );
}
