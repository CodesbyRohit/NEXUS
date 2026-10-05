import type { Comparison, Decision } from "../types";
import { PRIORITY_STYLE } from "../theme";

interface Props {
  decision: Decision;
  comparison?: Comparison | null;
  onSelectNode?: (id: string) => void;
}

export default function DecisionCard({ decision, comparison }: Props) {
  const style = PRIORITY_STYLE[decision.priority] ?? PRIORITY_STYLE.LOW;
  const maxWeight = Math.max(...decision.risk_factors.map((f) => f.weight), 1);

  return (
    <div className="rounded-lg border border-base-700 bg-base-850">
      <div className="flex items-center justify-between border-b border-base-700 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className={`chip ${style}`}>{decision.priority}</span>
          <span className="text-[11px] text-slate-400">
            risk score <span className="font-mono text-slate-200">{decision.score}</span>
          </span>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="text-slate-400">
            confidence <span className="font-mono text-slate-200">{Math.round(decision.confidence * 100)}%</span>
          </span>
          <span
            className={`chip ${
              decision.recommend_human_review
                ? "border-red-500/40 bg-red-500/10 text-red-300"
                : "border-base-600 bg-base-800 text-slate-400"
            }`}
          >
            {decision.recommend_human_review ? "HUMAN REVIEW" : "AUTO-TRIAGE"}
          </span>
        </div>
      </div>

      <div className="px-3 py-2 space-y-1.5">
        <div className="text-[10px] uppercase tracking-widest text-slate-500">
          Risk factors (graph-derived)
        </div>
        {decision.risk_factors.map((f) => (
          <div key={f.factor} className="flex items-center gap-2">
            <span className="w-[130px] shrink-0 font-mono text-[10px] text-slate-400">
              {f.factor}
            </span>
            <span className="h-1.5 flex-1 rounded bg-base-800">
              <span
                className="block h-1.5 rounded bg-accent/70"
                style={{ width: `${(f.weight / maxWeight) * 100}%` }}
              />
            </span>
            <span className="w-8 shrink-0 text-right font-mono text-[10px] text-slate-300">
              +{f.weight}
            </span>
          </div>
        ))}
        <p className="pt-1 text-[11px] text-slate-500">
          policy <span className="font-mono">{decision.policy_version}</span>
        </p>
      </div>

      {comparison && comparison.changed && (
        <div className="border-t border-base-700 px-3 py-2">
          <div className="text-[10px] uppercase tracking-widest text-slate-500">
            Decision changed
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs">
            <span className={`chip ${PRIORITY_STYLE[comparison.before.priority] ?? ""}`}>
              {comparison.before.priority} · {comparison.before.score}
            </span>
            <span className="text-slate-500">→</span>
            <span className={`chip ${PRIORITY_STYLE[comparison.after.priority] ?? ""}`}>
              {comparison.after.priority} · {comparison.after.score}
            </span>
            <span className="font-mono text-[11px] text-emerald-300">
              {comparison.score_delta > 0 ? "+" : ""}
              {comparison.score_delta}
            </span>
          </div>
          {comparison.new_risk_factors.length > 0 && (
            <ul className="mt-1.5 space-y-0.5">
              {comparison.new_risk_factors.map((f) => (
                <li key={f.factor} className="text-[11px] text-emerald-300">
                  + new evidence: {f.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
