import type { ReactNode } from "react";

/** Inline `**bold**` only; unmatched `**` stays literal. */
function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[\s\S]*?\*\*)/g);
  return parts.map((part, i) => {
    if (
      part.startsWith("**") &&
      part.endsWith("**") &&
      part.length >= 4
    ) {
      return (
        <strong
          key={i}
          className="break-words font-bold text-spire-primary"
        >
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

/**
 * Minimal markdown for tactical prompts: ATX headings (#–###) and **bold**.
 * No links, lists, or HTML — safe to render LLM/game text as React nodes.
 */
export function renderPromptMarkdown(text: string): ReactNode {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let para: string[] = [];
  let key = 0;

  const flushParagraph = () => {
    if (para.length === 0) return;
    const body = para.join("\n");
    para = [];
    blocks.push(
      <p
        key={key++}
        className="mb-2 whitespace-pre-wrap break-words text-spire-primary last:mb-0"
      >
        {renderInline(body)}
      </p>,
    );
  };

  for (const line of lines) {
    if (line === "") {
      flushParagraph();
      continue;
    }

    let heading: { level: 1 | 2 | 3; content: string } | null = null;
    if (/^###\s+/.test(line)) {
      heading = { level: 3, content: line.replace(/^###\s+/, "") };
    } else if (/^##\s+/.test(line)) {
      heading = { level: 2, content: line.replace(/^##\s+/, "") };
    } else if (/^#\s+/.test(line)) {
      heading = { level: 1, content: line.replace(/^#\s+/, "") };
    }

    if (heading) {
      flushParagraph();
      const { level, content } = heading;
      const className =
        level === 1
          ? "mb-2 mt-1 min-w-0 break-words font-console text-xl font-bold uppercase tracking-[0.06em] text-spire-primary first:mt-0"
          : level === 2
            ? "mb-1.5 mt-2 min-w-0 break-words font-console text-lg font-bold uppercase tracking-[0.08em] text-spire-primary first:mt-0"
            : "mb-1.5 mt-1.5 min-w-0 break-words font-console text-base font-semibold uppercase tracking-[0.1em] text-spire-label first:mt-0";
      const Tag = level === 1 ? "h1" : level === 2 ? "h2" : "h3";
      blocks.push(
        <Tag key={key++} className={className}>
          {renderInline(content)}
        </Tag>,
      );
    } else {
      para.push(line);
    }
  }
  flushParagraph();

  return (
    <div className="min-w-0 max-w-full space-y-1 overflow-x-hidden">{blocks}</div>
  );
}
