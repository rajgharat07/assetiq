import React from "react";

/** Clean Gemma prose: drop markdown tables (visual already shows them), keep light bold. */
export function cleanSummary(text, visualType) {
  if (!text) return "";
  let t = String(text);
  // Remove fenced code blocks
  t = t.replace(/```[\s\S]*?```/g, "");
  // Always strip markdown tables — UI Visuals already render the chart/table
  // Multi-line pipe tables
  t = t.replace(/(?:^|\n)(?:\|[^\n]*\|(?:\r?\n|$))+/g, "\n");
  // Separator rows (| :--- | :--- |)
  t = t.replace(/(?:^|\n)\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?(?:\n|$)/g, "\n");
  // Any remaining line with 2+ pipes (Gemma sometimes dumps one long pipe row)
  t = t
    .split("\n")
    .filter((line) => (line.match(/\|/g) || []).length < 2)
    .join("\n");
  // Collapse leftover inline pipe junk: "foo | bar | baz" → drop if mostly pipes
  t = t.replace(/(?:^|\s)\|[^|\n]+\|[^|\n]*(?:\|[^|\n]*)+/g, " ");
  // Heading hashes
  t = t.replace(/^#{1,6}\s+/gm, "");
  t = t.replace(/\n{3,}/g, "\n\n").trim();
  // If stripping emptied a table-heavy reply, fall back to a short line
  if (!t && visualType && visualType !== "none") {
    return "";
  }
  return t;
}

function renderInline(text) {
  // **bold**, *italic*, `code` → React nodes
  const parts = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      parts.push(
        <code key={key++} style={{ fontSize: "0.9em" }}>
          {token.slice(1, -1)}
        </code>
      );
    } else {
      parts.push(<em key={key++}>{token.slice(1, -1)}</em>);
    }
    last = m.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length ? parts : text;
}

export default function Summary({ text, visualType }) {
  const cleaned = cleanSummary(text, visualType);
  if (!cleaned) return null;
  const paragraphs = cleaned.split(/\n+/).filter(Boolean);
  return (
    <div className="summary">
      {paragraphs.map((p, i) => (
        <p key={i} style={{ margin: "0.35rem 0", whiteSpace: "pre-wrap" }}>
          {renderInline(p)}
        </p>
      ))}
    </div>
  );
}
