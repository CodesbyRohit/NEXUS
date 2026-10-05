import { useEffect, useRef, useState } from "react";
import type { Message } from "../types";
import DecisionCard from "./DecisionCard";

interface Props {
  messages: Message[];
  loading: boolean;
  onSend: (question: string) => void;
  onSelectNode: (id: string) => void;
}

const SUGGESTIONS = [
  "What is the most dangerous unresolved incident?",
  "Why is Incident #142 critical?",
  "What caused this failure?",
  "Has this happened before?",
  "What services are affected?",
  "Who owns the affected service?",
  "What should we do now?",
  "Show me the evidence path",
  "Checkout traffic increased 34%.",
  "Re-evaluate the incident.",
  "Why did your recommendation change?",
];

export default function CommandPanel({ messages, loading, onSend, onSelectNode }: Props) {
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  const submit = () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    onSend(q);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="panel-header">
        <span>AI Command</span>
        <span className="text-[10px] normal-case tracking-normal text-slate-500">
          every answer is graph-grounded
        </span>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3">
        {messages.length === 0 && (
          <div className="space-y-3 text-sm text-slate-400">
            <p>
              NEXUS reasons over a living knowledge graph of services, incidents, history and
              business impact. Ask it anything about the current incident landscape.
            </p>
            <p className="text-[11px] text-slate-500">
              Tip: start with the first suggestion, then ask <em>Why?</em>
            </p>
          </div>
        )}

        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-sm text-slate-100">
                {m.text}
              </div>
            </div>
          ) : (
            <div key={m.id} className="space-y-2">
              <div
                className={`rounded-lg border px-3 py-2.5 text-sm leading-relaxed ${
                  m.error
                    ? "border-red-500/40 bg-red-500/5 text-red-200"
                    : "border-base-700 bg-base-850 text-slate-200"
                }`}
              >
                <div className="mb-1.5 flex items-center gap-2 text-[10px] uppercase tracking-widest text-slate-500">
                  <span>{m.result?.intent?.replace(/_/g, " ") ?? "answer"}</span>
                  {m.result && (
                    <>
                      <span className="text-slate-600">·</span>
                      <span className="font-mono">
                        {Math.round(m.result.confidence * 100)}% confidence
                      </span>
                      <span className="text-slate-600">·</span>
                      <span
                        className={
                          m.result.mode === "llm" ? "text-violet-300" : "text-slate-500"
                        }
                      >
                        {m.result.mode === "llm" ? "LLM narration" : "deterministic"}
                      </span>
                    </>
                  )}
                </div>
                <p className="whitespace-pre-wrap">{m.text}</p>
              </div>

              {m.result?.decision && (
                <DecisionCard decision={m.result.decision} comparison={m.result.comparison} />
              )}

              {m.result && m.result.reasoning.length > 0 && (
                <details className="rounded-lg border border-base-700 bg-base-900 px-3 py-2">
                  <summary className="cursor-pointer text-[10px] uppercase tracking-widest text-slate-500">
                    Reasoning ({m.result.reasoning.length} steps)
                  </summary>
                  <ul className="mt-2 space-y-1">
                    {m.result.reasoning.map((r, i) => (
                      <li key={i} className="text-[11px] text-slate-400">
                        <span className="font-mono text-slate-600">{i + 1}.</span> {r}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {m.result?.mutations && m.result.mutations.length > 0 && (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-emerald-400">
                    Graph updated
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {m.result.mutations.map((mu, i) => (
                      <li key={i} className="font-mono text-[11px] text-emerald-200">
                        {mu.type === "create_node"
                          ? `CREATE (${mu.label} {id: '${mu.id}'})`
                          : `CREATE ()-[:${mu.rel}]-> (${mu.target})`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {m.result?.ranked && m.result.ranked.length > 1 && (
                <div className="rounded-lg border border-base-700 bg-base-900 px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-slate-500">
                    Unresolved incidents, ranked by graph score
                  </div>
                  <ul className="mt-1.5 space-y-1">
                    {m.result.ranked.slice(0, 5).map((r) => (
                      <li key={r.id}>
                        <button
                          className="flex w-full items-center gap-2 rounded px-1 py-0.5 text-left text-[11px] hover:bg-base-800"
                          onClick={() => onSelectNode(r.id)}
                          title="Inspect this incident"
                        >
                          <span className="font-mono text-slate-500">{r.id}</span>
                          <span className="flex-1 truncate text-slate-300">{r.title}</span>
                          <span className="font-mono text-slate-400">{r.score}</span>
                          <span className="chip border-base-600 text-slate-300">{r.priority}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ),
        )}

        {loading && (
          <div className="flex items-center gap-2 text-[11px] text-slate-500">
            <span className="live-dot inline-block h-2 w-2 rounded-full bg-accent" />
            traversing FalkorDB…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t border-base-700 px-3 py-2">
        <div className="mb-2 flex flex-wrap gap-1.5" data-testid="suggestions">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              className="rounded border border-base-600 bg-base-850 px-2 py-1 text-[10px] text-slate-400 transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40"
              onClick={() => onSend(s)}
              disabled={loading}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            data-testid="command-input"
            className="flex-1 rounded border border-base-600 bg-base-850 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-accent/50 focus:outline-none"
            placeholder="Ask about incidents, causes, impact, ownership…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            disabled={loading}
          />
          <button className="btn-primary" onClick={submit} disabled={loading || !input.trim()}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
