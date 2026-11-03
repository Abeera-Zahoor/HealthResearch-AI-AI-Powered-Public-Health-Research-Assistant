import type { Audience, OutputType, RunStatus, Strength, Support, RefStatus } from "../types";

export const AUDIENCE_OPTIONS: { value: Audience; label: string }[] = [
  { value: "general_public", label: "General public" },
  { value: "patients", label: "Patients and caregivers" },
  { value: "clinicians", label: "Healthcare professionals" },
  { value: "policymakers", label: "Policymakers" },
  { value: "students", label: "Students" },
  { value: "journalists", label: "Journalists" },
];

export const OUTPUT_OPTIONS: { value: OutputType; label: string }[] = [
  { value: "research_summary", label: "Research summary" },
  { value: "public_health_article", label: "Public health article" },
  { value: "social_media_posts", label: "Social media posts" },
  { value: "video_script", label: "Short video script" },
];

export const PAPER_COUNT_OPTIONS = [5, 8, 10, 15, 20];

export const audienceLabel = (value: Audience) => AUDIENCE_OPTIONS.find((o) => o.value === value)?.label ?? value;
export const outputLabel = (value: OutputType) => OUTPUT_OPTIONS.find((o) => o.value === value)?.label ?? value;

export const STATUS_LABEL: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export const STRENGTH_LABEL: Record<Strength, string> = {
  strong: "Strong design",
  moderate: "Moderate design",
  limited: "Limited design",
};

export const SUPPORT_LABEL: Record<Support, string> = {
  supported: "Supported",
  partial: "Partly supported",
  unsupported: "Unverified",
};

export const REF_STATUS_LABEL: Record<RefStatus, string> = {
  verified: "Verified",
  partial: "Partly verified",
  flagged: "Flagged",
};

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function durationSeconds(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return Number.isFinite(ms) && ms >= 0 ? Math.round(ms / 1000) : null;
}
