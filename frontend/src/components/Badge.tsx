import type { ReactNode } from "react";

export type Tone = "good" | "warn" | "bad" | "neutral" | "info";

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export const supportTone = (support: string): Tone => (support === "supported" ? "good" : support === "partial" ? "warn" : "bad");
export const refTone = (status: string): Tone => (status === "verified" ? "good" : status === "partial" ? "warn" : "bad");
export const strengthTone = (strength: string): Tone => (strength === "strong" ? "good" : strength === "moderate" ? "info" : "neutral");
