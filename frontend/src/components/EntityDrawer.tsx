import type { EntityResponse } from "../types";
import { labelColor } from "../theme";

interface Props {
  entity: EntityResponse | null;
  loading: boolean;
  onClose: () => void;
  onSelectNode: (id: string) => void;
}

function fmt(value: unknown): string {
  if (typeof value === "number") return value.toLocaleString();
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

export default function EntityDrawer({ entity, loading, onClose, onSelectNode }: Props) {
  if (!entity && !loading) return null;

  return (
    <aside className="absolute right-0 top-0 z-20 flex h-full w-[420px] max-w-[92vw] flex-col border-l border-base-700 bg-base-900 shadow-2xl">
      <div className="flex items-center justify-between border-b border-base-700 px-3 py-2">
        <span className="text-[11px] uppercase tracking-widest text-slate-500">
          Entity inspector
        </span>
        <button className="btn-ghost px-2 py-0.5 text-xs" onClick={onClose}>
          Close
        </button>
      </div>

      {loading && !entity ? (
        <div className="p-4 text-sm text-slate-500">Loading neighbourhood…</div>
      ) : entity ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3 space-y-4">
          <div>
            <div className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ background: labelColor(entity.node.label) }}
              />
              <span className="text-[11px] uppercase tracking-widest text-slate-500">
                {entity.node.label}
              </span>
            </div>
            <h2 className="mt-1 text-base font-semibold text-slate-100">{entity.node.name}</h2>
            <div className="font-mono text-[11px] text-slate-500">{entity.node.id}</div>
          </div>

          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Properties</div>
            <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
              {Object.entries(entity.node.props)
                .filter(([k]) => k !== "id")
                .map(([k, v]) => (
                  <div key={k} className="col-span-1 min-w-0">
                    <dt className="truncate font-mono text-[10px] text-slate-500">{k}</dt>
                    <dd className="truncate text-[11px] text-slate-300" title={fmt(v)}>
                      {fmt(v)}
                    </dd>
                  </div>
                ))}
            </dl>
          </div>

          {entity.ownership?.team && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">
                Ownership
              </div>
              <div className="mt-1 text-[12px] text-slate-200">
                {entity.ownership.team.name}{" "}
                <span className="font-mono text-[11px] text-slate-500">
                  {entity.ownership.team.slack}
                </span>
              </div>
              {entity.ownership.on_call.length > 0 && (
                <div className="mt-1 text-[11px] text-slate-400">
                  on-call:{" "}
                  {entity.ownership.on_call.map((p) => (
                    <button
                      key={p.id}
                      className="mr-2 text-accent hover:underline"
                      onClick={() => onSelectNode(p.id)}
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {entity.runbooks.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">Runbooks</div>
              <ul className="mt-1 space-y-1">
                {entity.runbooks.map((r) => (
                  <li key={r.id} className="text-[11px] text-slate-300">
                    • {r.title}{" "}
                    <span className="font-mono text-[10px] text-slate-600">{r.steps} steps</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">
              History ({entity.history.length})
            </div>
            <ul className="mt-1 space-y-1">
              {entity.history.slice(0, 14).map((h) => (
                <li key={h.id + h.rel} className="flex items-start gap-2 text-[11px]">
                  <span className="rounded bg-base-800 px-1.5 py-0.5 font-mono text-[10px] text-accent">
                    {h.rel}
                  </span>
                  <button
                    className="flex-1 text-left text-slate-300 hover:underline"
                    onClick={() => onSelectNode(h.id)}
                  >
                    {h.text}
                  </button>
                  <span className="shrink-0 font-mono text-[10px] text-slate-600">
                    {h.at ? h.at.slice(0, 10) : ""}
                  </span>
                </li>
              ))}
              {entity.history.length === 0 && (
                <li className="text-[11px] text-slate-500">No events, incidents or decisions.</li>
              )}
            </ul>
          </div>

          {entity.decisions.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">
                Decisions involving this entity
              </div>
              <ul className="mt-1 space-y-1">
                {entity.decisions.map((d) => (
                  <li key={d.id} className="text-[11px] text-slate-300">
                    <span className="text-slate-500">{d.question}</span>
                    <div className="text-[10px] text-slate-400">{d.answer}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">
              Direct neighbourhood ({entity.neighborhood.nodes.length - 1} nodes)
            </div>
            <ul className="mt-1 flex flex-wrap gap-1">
              {entity.neighborhood.nodes
                .filter((n) => n.id !== entity.node.id)
                .slice(0, 30)
                .map((n) => (
                  <li key={n.id}>
                    <button
                      className="rounded border border-base-600 bg-base-850 px-1.5 py-0.5 text-[10px] hover:border-accent/40"
                      style={{ color: labelColor(n.label) }}
                      onClick={() => onSelectNode(n.id)}
                    >
                      {n.name}
                    </button>
                  </li>
                ))}
            </ul>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
