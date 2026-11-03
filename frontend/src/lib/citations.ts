// Turns the (markdown-like) text produced by the Health Education Agent into safe, structured blocks.
// Nothing here uses dangerouslySetInnerHTML: React renders every piece as plain text.

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "cite"; ids: string[] }
  | { kind: "unverified" };

export type Block =
  | { kind: "heading"; level: 2 | 3; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; lines: string[] };

const TOKEN = /\*\*([^*]+)\*\*|\[(S\d+(?:\s*,\s*S\d+)*)\]|(\[unverified source\])/g;

export function tokenizeInline(text: string): Inline[] {
  const tokens: Inline[] = [];
  let last = 0;
  for (const match of text.matchAll(TOKEN)) {
    const index = match.index ?? 0;
    if (index > last) tokens.push({ kind: "text", text: text.slice(last, index) });
    if (match[1] !== undefined) tokens.push({ kind: "bold", text: match[1] });
    else if (match[2] !== undefined) tokens.push({ kind: "cite", ids: match[2].split(",").map((id) => id.trim()) });
    else tokens.push({ kind: "unverified" });
    last = index + match[0].length;
  }
  if (last < text.length) tokens.push({ kind: "text", text: text.slice(last) });
  return tokens;
}

export function parseBlocks(content: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", lines: paragraph });
    if (list.length) blocks.push({ kind: "list", items: list });
    paragraph = [];
    list = [];
  };

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    if (!line) {
      flush();
    } else if (heading) {
      flush();
      blocks.push({ kind: "heading", level: heading[1].length === 3 ? 3 : 2, text: heading[2] });
    } else if (bullet) {
      if (paragraph.length) flush();
      list.push(bullet[1]);
    } else {
      if (list.length) flush();
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}

/** Every distinct source id cited in a piece of text, in order of first appearance. */
export function citedIds(text: string): string[] {
  const ids: string[] = [];
  for (const token of tokenizeInline(text)) {
    if (token.kind === "cite") for (const id of token.ids) if (!ids.includes(id)) ids.push(id);
  }
  return ids;
}
