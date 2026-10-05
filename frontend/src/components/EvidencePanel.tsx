import { useState } from "react";
import type { QueryResult } from "../types";
import { labelColor } from "../theme";

interface Props {
  result: QueryResult | null;
  onSelectNode: (id: string) => void;
}

export default function EvidencePanel({ result, onSelectNode }: Props) {
  const [tab, setTab] = useState<"path" | "trace">("path");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-base-700 bg-base-900 px-2">
        <button
          className={`px-3 py-2 text-[11px] uppercase tracking-widest ${
            tab === "path" ? "border-b-2 border-accent text-accent" : "text-slate-500"
          }`}
          onClick={() => setTab("path")}
        >
          Evidence path
        </button>
        <button
          className={`px-3 py-2 text-[11px] uppercase tracking-widest ${
            tab === "trace" ? "border-b-2 border-accent text-accent" : "text-slate-500"
          }`}
          onClick={() => setTab("trace")}
        >
          Decision trace / observability
        </button>
        {result?.evidence_path && tab === "path" && (
          <span className="ml-auto pr-2 text-[10px] text-slate-500">
            {result.evidence_path.hops.length} graph relationships · click a hop to inspect
          </span>
        )}
        {result?.trace && tab === "trace" && (
          <span className="ml-auto pr-2 font-mono text-[10px] text-slate-500">
            {result.trace.query_count} Cypher queries · mode {result.trace.mode}
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-3 py-2">
        {!result && (
          <p className="text-[11px] text-slate-500">
            Ask a question and NEXUS will show the exact graph relationships that produced the
            answer.
          </p>
        )}

        {result && tab === "path" && (
          <div className="space-y-1.5">
            {!result.evidence_path || result.evidence_path.hops.length === 0 ? (
              <p className="text-[11px] text-slate-500">
                This answer did not require a causal path (e.g. a memory write). Ask “Why is
                Incident #142 critical?” to see one.
              </p>
            ) : (
              result.evidence_path.hops.map((h, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded border border-base-700 bg-base-850 px-2 py-1.5"
                >
                  <span className="w-6 shrink-0 pt-0.5 text-right font-mono text-[10px] text-slate-600">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                      <button
                        className="font-medium hover:underline"
                        style={{ color: labelColor(h.from.label) }}
                        onClick={() => onSelectNode(h.from.id)}
                      >
                        {h.from.name}
                      </button>
                      <span className="rounded bg-base-800 px-1.5 py-0.5 font-mono text-[10px] text-accent">
                        {h.rel}
                      </span>
                      <button
                        className="font-medium hover:underline"
                        style={{ color: labelColor(h.to.label) }}
                        onClick={() => onSelectNode(h.to.id)}
                      >
                        {h.to.name}
                      </button>
                    </div>
                    <div className="text-[10px] text-slate-500">{h.why}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {result && tab === "trace" && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">Pipeline</div>
              <ol className="mt-1 space-y-1 text-[11px] text-slate-400">
                <li>
                  <span className="text-slate-600">query:</span> {result.trace.user_query}
                </li>
                <li>
                  <span className="text-slate-600">intent:</span>{" "}
                  <span className="font-mono text-accent">{result.trace.intent}</span>
                </li>
                <li>
                  <span className="text-slate-600">cypher queries:</span>{" "}
                  <span className="font-mono">{result.trace.query_count}</span>
                </li>
                <li>
                  <span className="text-slate-600">nodes retrieved:</span>{" "}
                  <span className="font-mono">{result.trace.retrieved_nodes.length}</span>
                </li>
                <li>
                  <span className="text-slate-600">relationships retrieved:</span>{" "}
                  <span className="font-mono">
                    {result.trace.retrieved_relationships.length}
                  </span>
                </li>
                <li>
                  <span className="text-slate-600">decision:</span>{" "}
                  {result.trace.decision
                    ? `${result.trace.decision.priority} (${result.trace.decision.score})`
                    : "—"}
                </li>
                <li>
                  <span className="text-slate-600">graph mutations:</span>{" "}
                  <span className="font-mono">{result.trace.graph_mutations.length}</span>
                </li>
              </ol>
            </div>

            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-slate-500">
                Retrieved relationships
              </div>
              <ul className="mt-1 max-h-40 space-y-0.5 overflow-auto font-mono text-[10px] text-slate-400">
                {result.trace.retrieved_relationships.map((r, i) => (
                  <li key={i}>
                    {r.source} -[{r.rel}]→ {r.target}
                  </li>
                ))}
              </ul>
            </div>

            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-slate-500">
                Executed Cypher
              </div>
              <ul className="mt-1 max-h-40 space-y-0.5 overflow-auto font-mono text-[10px] text-slate-500">
                {result.trace.graph_queries.slice(0, 60).map((q, i) => (
                  <li key={i} className="truncate" title={q}>
                    {q}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
