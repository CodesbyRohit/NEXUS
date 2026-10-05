import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import CommandPanel from "./components/CommandPanel";
import EntityDrawer from "./components/EntityDrawer";
import EvidencePanel from "./components/EvidencePanel";
import GraphView from "./components/GraphView";
import Header from "./components/Header";
import type { EntityResponse, Graph, Health, Message, QueryResult, Stats } from "./types";

const DEMO_FOCUS = "inc-142";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState<QueryResult | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [entity, setEntity] = useState<EntityResponse | null>(null);
  const [entityLoading, setEntityLoading] = useState(false);
  const [offline, setOffline] = useState<string | null>(null);
  const [reseeding, setReseeding] = useState(false);

  const sessionId = useMemo(
    () => `session-${Math.random().toString(36).slice(2, 10)}`,
    [],
  );

  const refreshStatus = useCallback(async () => {
    try {
      const [h, s] = await Promise.all([api.health(), api.stats()]);
      setHealth(h);
      setStats(s);
      setOffline(h.ok ? null : h.error ?? "graph unavailable");
    } catch (err) {
      setHealth(null);
      setOffline(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refreshStatus();
      try {
        setGraph(await api.overview(DEMO_FOCUS, 2));
      } catch {
        /* handled by the offline banner */
      }
    })();
  }, [refreshStatus]);

  // Highlight the evidence path currently displayed on the graph.
  const { activeNodeIds, activeEdgeKeys } = useMemo(() => {
    const nodes = new Set<string>();
    const edges = new Set<string>();
    const path = lastResult?.evidence_path;
    if (path && path.hops.length > 0) {
      for (const h of path.hops) {
        nodes.add(h.from.id);
        nodes.add(h.to.id);
        edges.add(`${h.from.id}|${h.rel}|${h.to.id}`);
      }
    }
    return { activeNodeIds: nodes, activeEdgeKeys: edges };
  }, [lastResult]);

  const send = useCallback(
    async (question: string) => {
      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: "user",
        text: question,
      };
      setMessages((m) => [...m, userMsg]);
      setLoading(true);
      try {
        const result = await api.query(question, sessionId);
        setMessages((m) => [
          ...m,
          { id: `a-${Date.now()}`, role: "agent", text: result.answer, result },
        ]);
        setLastResult(result);
        if (result.graph && result.graph.nodes.length > 0) {
          setGraph(result.graph);
        }
        void refreshStatus();
      } catch (err) {
        setMessages((m) => [
          ...m,
          {
            id: `e-${Date.now()}`,
            role: "agent",
            text: `Could not reach the NEXUS API: ${
              err instanceof Error ? err.message : String(err)
            }`,
            error: true,
          },
        ]);
        setOffline(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [refreshStatus, sessionId],
  );

  const selectNode = useCallback(
    async (id: string) => {
      setSelectedId(id);
      const inGraph = graph.nodes.some((n) => n.id === id);
      setEntityLoading(true);
      try {
        const detail = await api.entity(id);
        setEntity(detail);
        if (!inGraph) setGraph(detail.neighborhood);
      } catch {
        setEntity(null);
      } finally {
        setEntityLoading(false);
      }
    },
    [graph.nodes],
  );

  const reseed = useCallback(async () => {
    setReseeding(true);
    try {
      await fetch(`${api.base}/api/seed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset: true }),
      });
      setMessages([]);
      setLastResult(null);
      setEntity(null);
      setSelectedId(null);
      await refreshStatus();
      setGraph(await api.overview(DEMO_FOCUS, 2));
    } finally {
      setReseeding(false);
    }
  }, [refreshStatus]);

  return (
    <div className="flex h-screen flex-col bg-base-950">
      <Header health={health} stats={stats} onReseed={reseed} reseeding={reseeding} />

      {offline && (
        <div className="border-b border-red-500/40 bg-red-500/10 px-4 py-2 text-[12px] text-red-200">
          FalkorDB is not reachable ({offline}). Start it with{" "}
          <code className="font-mono text-red-100">docker compose up -d</code> in the repo root,
          then make sure <code className="font-mono text-red-100">FALKORDB_HOST/PORT</code> match.
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <section className="flex min-h-0 w-[38%] min-w-[360px] max-w-[560px] flex-col border-r border-base-700">
          <CommandPanel
            messages={messages}
            loading={loading}
            onSend={send}
            onSelectNode={selectNode}
          />
        </section>

        <section className="relative min-h-0 min-w-0 flex-1">
          <div className="absolute inset-x-3 top-3 z-10 flex items-center justify-between">
            <span className="rounded bg-base-950/70 px-2 py-1 text-[10px] uppercase tracking-widest text-slate-400">
              Knowledge graph
            </span>
            {lastResult?.evidence_path && (
              <span className="rounded bg-base-950/70 px-2 py-1 text-[10px] text-slate-400">
                highlighted: {lastResult.evidence_path.hops.length} relationships on the evidence
                path
              </span>
            )}
          </div>

          <GraphView
            graph={graph}
            activeNodeIds={activeNodeIds}
            activeEdgeKeys={activeEdgeKeys}
            selectedId={selectedId}
            onSelect={selectNode}
          />

          <EntityDrawer
            entity={entity}
            loading={entityLoading}
            onClose={() => {
              setSelectedId(null);
              setEntity(null);
            }}
            onSelectNode={selectNode}
          />
        </section>
      </div>

      <div className="h-[248px] shrink-0 border-t border-base-700 bg-base-900">
        <EvidencePanel result={lastResult} onSelectNode={selectNode} />
      </div>
    </div>
  );
}
