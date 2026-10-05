/** Shared visual language for the command center. */

export const LABEL_COLORS: Record<string, string> = {
  Incident: "#f87171",
  Service: "#38bdf8",
  Database: "#a78bfa",
  API: "#22d3ee",
  System: "#818cf8",
  Team: "#fbbf24",
  Person: "#94a3b8",
  Impact: "#f472b6",
  Event: "#64748b",
  Decision: "#34d399",
  Action: "#fb923c",
  Customer: "#475569",
  Transaction: "#334155",
  Runbook: "#2dd4bf",
  Document: "#94a3b8",
  Evidence: "#7dd3fc",
  Session: "#475569",
  Question: "#64748b",
  Unknown: "#64748b",
};

export function labelColor(label: string): string {
  return LABEL_COLORS[label] ?? "#64748b";
}

export function withAlpha(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export const PRIORITY_STYLE: Record<string, string> = {
  CRITICAL: "bg-red-500/15 border-red-500/50 text-red-300",
  HIGH: "bg-orange-500/15 border-orange-500/50 text-orange-300",
  MEDIUM: "bg-amber-500/15 border-amber-500/50 text-amber-200",
  LOW: "bg-emerald-500/15 border-emerald-500/50 text-emerald-300",
};

export const SEVERITY_STYLE: Record<string, string> = {
  sev1: "text-red-400",
  sev2: "text-orange-300",
  sev3: "text-amber-300",
  sev4: "text-slate-400",
  critical: "text-red-400",
};

/** Node kinds that are worth showing in the legend. */
export const LEGEND_LABELS = [
  "Incident",
  "Service",
  "Database",
  "API",
  "Impact",
  "Team",
  "Event",
  "Decision",
  "Action",
];
