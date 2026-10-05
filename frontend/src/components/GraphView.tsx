import { useCallback, useEffect, useMemo, useRef } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { Graph } from "../types";
import { LEGEND_LABELS, labelColor, withAlpha } from "../theme";

interface Props {
  graph: Graph;
  activeNodeIds: Set<string>;
  activeEdgeKeys: Set<string>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

interface FNode {
  id: string;
  name: string;
  label: string;
  x?: number;
  y?: number;
}

export default function GraphView({
  graph,
  activeNodeIds,
  activeEdgeKeys,
  selectedId,
  onSelect,
}: Props) {
  // react-force-graph mutates its node objects, so build a fresh dataset and
  // keep the structure stable until the graph itself changes.
  const data = useMemo(() => {
    const seen = new Set<string>();
    const nodes: FNode[] = [];
    for (const n of graph.nodes) {
      if (seen.has(n.id)) continue;
      seen.add(n.id);
      nodes.push({ id: n.id, name: n.name, label: n.label });
    }
    const links = graph.edges
      .filter((e) => seen.has(e.source) && seen.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, rel: e.rel }));
    return { nodes, links };
  }, [graph]);

  const fg = useRef<{ zoomToFit?: (ms?: number, px?: number) => void } | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => fg.current?.zoomToFit?.(600, 60), 400);
    return () => window.clearTimeout(t);
  }, [data]);

  const hasHighlight = activeNodeIds.size > 0;

  const nodeCanvasObject = useCallback(
    (node: FNode, ctx: CanvasRenderingContext2D, scale: number) => {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const active = !hasHighlight || activeNodeIds.has(node.id);
      const selected = selectedId === node.id;
      const color = labelColor(node.label);
      const radius = selected ? 7 : node.label === "Incident" ? 6 : 4.5;

      if (active) {
        ctx.shadowColor = withAlpha(color, 0.85);
        ctx.shadowBlur = selected ? 18 : 10;
      } else {
        ctx.shadowBlur = 0;
      }

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = active ? color : withAlpha(color, 0.16);
      ctx.fill();
      ctx.shadowBlur = 0;

      if (selected) {
        ctx.beginPath();
        ctx.arc(x, y, radius + 4, 0, Math.PI * 2);
        ctx.strokeStyle = "#e2e8f0";
        ctx.lineWidth = 1.5 / scale;
        ctx.stroke();
      }

      if (active && (scale > 0.9 || selected || node.label === "Incident")) {
        const fontSize = Math.max(9 / scale, 2.6);
        ctx.font = `${fontSize}px ui-sans-serif, system-ui, sans-serif`;
        ctx.fillStyle = active ? "#cbd5e1" : "#475569";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        const text = node.name.length > 34 ? `${node.name.slice(0, 33)}…` : node.name;
        ctx.fillText(text, x, y + radius + 2 / scale);
      }
    },
    [activeNodeIds, hasHighlight, selectedId],
  );

  const linkColor = useCallback(
    (link: { source: string | { id: string }; target: string | { id: string }; rel: string }) => {
      const s = typeof link.source === "object" ? link.source.id : link.source;
      const t = typeof link.target === "object" ? link.target.id : link.target;
      const key = `${s}|${link.rel}|${t}`;
      const activeLink = !hasHighlight || activeEdgeKeys.has(key);
      if (!activeLink) return "rgba(71,85,105,0.16)";
      if (link.rel === "DEPENDS_ON") return "rgba(56,189,248,0.75)";
      if (link.rel === "CAUSED" || link.rel === "AFFECTS" || link.rel === "IMPACTS")
        return "rgba(248,113,113,0.75)";
      if (link.rel === "SUPPORTS") return "rgba(34,211,238,0.7)";
      return "rgba(148,163,184,0.45)";
    },
    [activeEdgeKeys, hasHighlight],
  );

  const linkWidth = useCallback(
    (link: { source: string | { id: string }; target: string | { id: string }; rel: string }) => {
      if (!hasHighlight) return 0.7;
      const s = typeof link.source === "object" ? link.source.id : link.source;
      const t = typeof link.target === "object" ? link.target.id : link.target;
      return activeEdgeKeys.has(`${s}|${link.rel}|${t}`) ? 2.1 : 0.4;
    },
    [activeEdgeKeys, hasHighlight],
  );

  return (
    <div className="relative h-full w-full">
      {data.nodes.length === 0 ? (
        <div className="flex h-full items-center justify-center text-sm text-slate-500">
          No graph data yet — ask NEXUS a question.
        </div>
      ) : (
        <ForceGraph2D
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ref={fg as any}
          graphData={data}
          backgroundColor="#0b1017"
          nodeCanvasObject={nodeCanvasObject as never}
          nodePointerAreaPaint={(node, color, ctx) => {
            const n = node as FNode;
            ctx.beginPath();
            ctx.arc(n.x ?? 0, n.y ?? 0, 9, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
          }}
          linkColor={linkColor as never}
          linkWidth={linkWidth as never}
          linkDirectionalParticles={(link) => {
            const l = link as { source: string | { id: string }; target: string | { id: string }; rel: string };
            const s = typeof l.source === "object" ? l.source.id : l.source;
            const t = typeof l.target === "object" ? l.target.id : l.target;
            return hasHighlight && activeEdgeKeys.has(`${s}|${l.rel}|${t}`) ? 2 : 0;
          }}
          linkDirectionalParticleWidth={2}
          linkDirectionalParticleColor={() => "#f8fafc"}
          onNodeClick={(node) => onSelect((node as FNode).id)}
          cooldownTicks={120}
          d3AlphaDecay={0.03}
          d3VelocityDecay={0.32}
          warmupTicks={30}
        />
      )}

      <div className="pointer-events-none absolute bottom-3 left-3 flex max-w-[70%] flex-wrap gap-x-3 gap-y-1 rounded bg-base-950/70 px-2 py-1.5 text-[10px] text-slate-400">
        {LEGEND_LABELS.map((l) => (
          <span key={l} className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: labelColor(l) }}
            />
            {l}
          </span>
        ))}
      </div>
    </div>
  );
}
