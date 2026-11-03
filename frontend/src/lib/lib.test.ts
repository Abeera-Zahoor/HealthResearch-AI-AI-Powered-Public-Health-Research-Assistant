import { describe, expect, it } from "vitest";
import { describeError } from "../api";
import type { ResearchRun } from "../types";
import { citedIds, parseBlocks, tokenizeInline } from "./citations";
import { runToMarkdown } from "./exportMarkdown";
import { durationSeconds } from "./format";

describe("tokenizeInline", () => {
  it("finds citations, bold text and the unverified marker", () => {
    expect(tokenizeInline("A **big** claim [S1, S2] and [unverified source].")).toEqual([
      { kind: "text", text: "A " },
      { kind: "bold", text: "big" },
      { kind: "text", text: " claim " },
      { kind: "cite", ids: ["S1", "S2"] },
      { kind: "text", text: " and " },
      { kind: "unverified" },
      { kind: "text", text: "." },
    ]);
  });

  it("leaves HTML-looking text as plain text (it is rendered by React, never as HTML)", () => {
    expect(tokenizeInline("<script>alert(1)</script>")).toEqual([{ kind: "text", text: "<script>alert(1)</script>" }]);
  });
});

describe("parseBlocks", () => {
  it("parses headings, bullet lists and paragraphs", () => {
    const blocks = parseBlocks("## Key findings\n- One [S1]\n- Two\n\nPlain text\nsecond line\n### Scene 1\nVisual: x");
    expect(blocks).toEqual([
      { kind: "heading", level: 2, text: "Key findings" },
      { kind: "list", items: ["One [S1]", "Two"] },
      { kind: "paragraph", lines: ["Plain text", "second line"] },
      { kind: "heading", level: 3, text: "Scene 1" },
      { kind: "paragraph", lines: ["Visual: x"] },
    ]);
  });

  it("returns nothing for empty text", () => {
    expect(parseBlocks("  \n \n")).toEqual([]);
  });
});

describe("citedIds", () => {
  it("lists each cited id once, in order", () => {
    expect(citedIds("a [S2] b [S1, S2] c [S3]")).toEqual(["S2", "S1", "S3"]);
  });
});

describe("describeError", () => {
  it("reads FastAPI validation errors", () => {
    const body = { detail: [{ msg: "Value error, Please enter a research question of at least 10 characters." }] };
    expect(describeError(body, 422)).toBe("Please enter a research question of at least 10 characters.");
  });
  it("reads plain detail strings and falls back to the status code", () => {
    expect(describeError({ detail: "That research run was not found." }, 404)).toBe("That research run was not found.");
    expect(describeError(null, 500)).toContain("HTTP 500");
  });
});

describe("durationSeconds", () => {
  it("computes whole seconds and tolerates missing values", () => {
    expect(durationSeconds("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:07+00:00")).toBe(7);
    expect(durationSeconds(null, "2026-01-01T00:00:07+00:00")).toBeNull();
  });
});

describe("runToMarkdown", () => {
  const run = {
    id: "r1",
    question: "Does exercise help mood in adults?",
    audience: "general_public",
    output_type: "research_summary",
    created_at: "2026-01-01T00:00:00+00:00",
    papers: [
      {
        ref_id: "S1",
        title: "A paper",
        authors: ["A B", "C D", "E F", "G H"],
        journal: "J",
        year: 2021,
        url: "https://pubmed.ncbi.nlm.nih.gov/1/",
      },
    ],
    analysis: { evidence_gaps: ["Gap one"], limitations: [] },
    citations: { counts: { references_verified: 1, claims_supported: 1 } },
    output: { title: "Title", content: "## Key findings\n- Thing [S1]", flags: ["Check this"], disclaimer: "Not medical advice." },
  } as unknown as ResearchRun;

  it("includes content, flags, gaps, verification counts, references and the disclaimer", () => {
    const md = runToMarkdown(run);
    expect(md).toContain("# Title");
    expect(md).toContain("- Thing [S1]");
    expect(md).toContain("## Flagged for review\n- Check this");
    expect(md).toContain("- Gap one");
    expect(md).toContain("1 verified");
    expect(md).toContain("[S1] A B, C D, E F et al. A paper. J, 2021. https://pubmed.ncbi.nlm.nih.gov/1/");
    expect(md).toContain("> Not medical advice.");
  });
});
