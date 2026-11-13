export type Service = {
  service: string;
  requests: number;
  error_rate: number;
  p50_ms: number;
  p95_ms: number;
};
export type Suspect = {
  service: string;
  score: number;
  evidence: string[];
  trace_id: string;
  p95_ms: number;
  baseline_p95_ms: number;
  error_rate: number;
  local_error_rate: number;
  recommendation: string;
};
export type Diagnosis = {
  status: 'healthy' | 'incident' | 'insufficient_data';
  suspects: Suspect[];
  method: string;
  caveats: string[];
  sample_count: number;
};
export type Incident = {
  id: string;
  created_at: number;
  ended_at: number;
  title: string;
  scenario_id: string;
  diagnosis: Diagnosis;
  services: Service[];
  ground_truth: string | null;
  top1_correct: boolean;
  timeline?: { at: number; message: string }[];
  trace_count: number;
  duration_seconds: number;
};
export type Scenario = {
  id: string;
  name: string;
  service: string | null;
  mode: string;
  description: string;
  category: string;
};
export type TraceRow = {
  trace_id: string;
  service: string;
  name: string;
  start_ns: number;
  duration_ms: number;
  error: boolean;
};
export type Span = TraceRow & {
  span_id: string;
  parent_id: string;
  end_ns: number;
  kind: number;
  attributes: Record<string, unknown>;
  events: { name: string; time_ns: number; attributes: Record<string, unknown> }[];
};
export type Overview = {
  now: number;
  window_seconds: number;
  lab: { phase: string; message: string; scenario: string | null; run_id?: string; last_run_id?: string };
  services: Service[];
  topology: { source: string; target: string; calls: number; errors: number; p95_ms: number }[];
  series: { at: number; requests: number; errors: number; p95_ms: number }[];
  request_count: number;
  span_count: number;
  error_rate: number;
  diagnosis: Diagnosis;
  incidents: Incident[];
  metric_source: string;
};
export type Report = {
  runs: number;
  fault_runs: number;
  control_runs: number;
  top1_accuracy: number | null;
  control_false_positive_rate: number | null;
  scope: string;
  incidents: Incident[];
};
