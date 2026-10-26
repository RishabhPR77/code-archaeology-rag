import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const SHA = /^[0-9a-f]{7,40}$/;

// Raw HTML in model output is never rendered — react-markdown escapes it by default
export function Markdown({ children, repoUrl }: { children: string; repoUrl?: string }) {
  return (
    <div className="prose-answer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          ),
          code: ({ children, className }) => {
            const text = String(children);
            // Inline commit SHAs link to the commit on GitHub
            if (!className && repoUrl && SHA.test(text)) {
              return (
                <a href={`${repoUrl}/commit/${text}`} target="_blank" rel="noopener noreferrer"
                   className="!no-underline">
                  <code className="!text-accent">{text}</code>
                </a>
              );
            }
            return <code className={className}>{children}</code>;
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
