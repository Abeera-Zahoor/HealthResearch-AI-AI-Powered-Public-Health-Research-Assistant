import type { Paper } from "../types";
import { parseBlocks, tokenizeInline } from "../lib/citations";

type PaperMap = Map<string, Paper>;

/** Renders one line of text, turning [S1] markers into clickable links to the real source. */
export function CitedText({ text, papers }: { text: string; papers: PaperMap }) {
  return (
    <>
      {tokenizeInline(text).map((token, index) => {
        if (token.kind === "text") return <span key={index}>{token.text}</span>;
        if (token.kind === "bold") return <strong key={index}>{token.text}</strong>;
        if (token.kind === "unverified") {
          return (
            <span key={index} className="cite cite-unknown" title="This citation did not match any retrieved paper and was removed.">
              unverified source
            </span>
          );
        }
        return (
          <span key={index} className="cite-group">
            [
            {token.ids.map((id, i) => {
              const paper = papers.get(id);
              return (
                <span key={id}>
                  {i > 0 && ", "}
                  {paper && paper.url ? (
                    <a className="cite" href={paper.url} target="_blank" rel="noopener noreferrer" title={paper.title}>
                      {id}
                    </a>
                  ) : (
                    <span className="cite cite-unknown" title="No such reference in this report">
                      {id}
                    </span>
                  )}
                </span>
              );
            })}
            ]
          </span>
        );
      })}
    </>
  );
}

/** Renders the whole generated text (headings, bullet lists, paragraphs) as safe React elements. */
export function RichText({ content, papers }: { content: string; papers: PaperMap }) {
  return (
    <div className="rich">
      {parseBlocks(content).map((block, index) => {
        if (block.kind === "heading") {
          const Tag = block.level === 2 ? "h3" : "h4";
          return (
            <Tag key={index}>
              <CitedText text={block.text} papers={papers} />
            </Tag>
          );
        }
        if (block.kind === "list") {
          return (
            <ul key={index}>
              {block.items.map((item, i) => (
                <li key={i}>
                  <CitedText text={item} papers={papers} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index}>
            {block.lines.map((line, i) => (
              <span key={i}>
                {i > 0 && <br />}
                <CitedText text={line} papers={papers} />
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
