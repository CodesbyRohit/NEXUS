import type { Health, Stats } from "../types";

interface Props {
  health: Health | null;
  stats: Stats | null;
  onReseed?: () => void;
  reseeding?: boolean;
}

export default function Header({ health, stats, onReseed, reseeding }: Props) {
  const online = health?.ok === true;
  return (
    <header className="flex items-center justify-between px-4 py-2.5 border-b border-base-700 bg-base-900">
      <div className="flex items-baseline gap-3">
        <span className="text-lg font-semibold tracking-[0.28em] text-slate-100">NEXUS</span>
        <span className="hidden md:inline text-[11px] text-slate-500">
          graph-native incident commander
        </span>
      </div>

      <div className="flex items-center gap-3 text-[11px]">
        <span className="flex items-center gap-1.5 text-slate-400">
          <span
            className={`live-dot inline-block h-2 w-2 rounded-full ${
              online ? "bg-emerald-400" : "bg-red-500"
            }`}
          />
          <span className={online ? "text-emerald-300" : "text-red-300"}>
            {online ? "GRAPH ONLINE" : "GRAPH OFFLINE"}
          </span>
        </span>

        {stats && (
          <span className="chip border-base-600 text-slate-300 font-mono">
            {stats.nodes.toLocaleString()} nodes · {stats.relationships.toLocaleString()} rels
          </span>
        )}

        <span
          className={`chip ${
            health?.llm_enabled
              ? "border-violet-500/40 text-violet-300 bg-violet-500/10"
              : "border-base-600 text-slate-400 bg-base-800"
          }`}
          title={
            health?.llm_enabled
              ? `LLM narration enabled (${health.llm_provider})`
              : "No LLM key configured — deterministic graph reasoning only"
          }
        >
          {health?.llm_enabled ? "LLM NARRATION" : "DETERMINISTIC MODE"}
        </span>

        {onReseed && (
          <button className="btn-ghost" onClick={onReseed} disabled={reseeding}>
            {reseeding ? "Seeding…" : "Reseed graph"}
          </button>
        )}
      </div>
    </header>
  );
}
