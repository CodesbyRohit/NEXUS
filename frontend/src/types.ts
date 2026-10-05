/** Shared types mirroring the NEXUS API responses. */

export interface GraphNode {
  id: string;
  label: string;
  name: string;
  props: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  rel: string;
  target: string;
  props?: Record<string, unknown>;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface HopEnd {
  id: string;
  label: string;
  name: string;
}

export interface Hop {
  from: HopEnd;
  rel: string;
  to: HopEnd;
  why: string;
}

export interface RiskFactor {
  factor: string;
  detail: string;
  weight: number;
}

export interface Decision {
  score: number;
  priority: string;
  recommend_human_review: boolean;
  risk_factors: RiskFactor[];
  confidence: number;
  policy_version: string;
}

export interface EvidencePath {
  incident: { id: string; name: string };
  hops: Hop[];
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface AssessmentSnapshot {
  priority: string;
  score: number;
  recommend_human_review: boolean;
  confidence: number;
  risk_factors: RiskFactor[];
}

export interface Comparison {
  changed: boolean;
  before: AssessmentSnapshot;
  after: AssessmentSnapshot;
  new_risk_factors: RiskFactor[];
  removed_risk_factors: RiskFactor[];
  score_delta: number;
}

export interface Trace {
  user_query: string;
  intent: string;
  graph_queries: string[];
  query_count: number;
  retrieved_nodes: { id: string; label: string; name: string }[];
  retrieved_relationships: { source: string; rel: string; target: string }[];
  decision: Decision | null;
  evidence_path: string[];
  graph_mutations: Mutation[];
  mode: string;
}

export interface Mutation {
  type: string;
  label?: string;
  id?: string;
  rel?: string;
  source?: string;
  target?: string;
  target_label?: string;
  summary?: string;
  [key: string]: unknown;
}

export interface RankedIncident {
  id: string;
  title: string;
  status: string;
  severity: string;
  service?: string;
  service_name?: string;
  score: number;
  priority: string;
  confidence: number;
  risk_factors: RiskFactor[];
}

export interface QueryResult {
  type: string;
  intent: string;
  answer: string;
  confidence: number;
  mode: "llm" | "deterministic";
  used_llm: boolean;
  decision: Decision | null;
  facts: Record<string, unknown>;
  evidence_path: EvidencePath | null;
  graph: Graph;
  reasoning: string[];
  ranked: RankedIncident[];
  comparison: Comparison | null;
  mutations: Mutation[];
  decision_id: string | null;
  session_id: string;
  trace: Trace;
}

export interface EntityResponse {
  node: GraphNode;
  neighborhood: Graph;
  history: { rel: string; label: string; id: string; text: string; at: string; status: string }[];
  decisions: { id: string; question: string; answer: string; priority?: string; at: string }[];
  ownership:
    | {
        team: { id: string; name: string; slack: string } | null;
        on_call: { id: string; name: string; email: string }[];
        members: { id: string; name: string; role: string }[];
      }
    | null;
  runbooks: { id: string; title: string; steps: number; targets: string[] }[];
}

export interface Stats {
  nodes: number;
  relationships: number;
  node_labels: Record<string, number>;
  relationship_types: Record<string, number>;
}

export interface Health {
  ok: boolean;
  host: string;
  port: number;
  graph: string;
  llm_enabled: boolean;
  llm_provider: string | null;
  mode: string;
  error?: string;
}

export interface Message {
  id: string;
  role: "user" | "agent";
  text: string;
  result?: QueryResult;
  error?: boolean;
}
