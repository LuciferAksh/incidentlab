import { useState } from 'react';
import { Activity, ArrowRight, Check, LoaderCircle, Radio } from 'lucide-react';
import { api, usePolling } from '../api';
import type { Baseline, Incident, Overview } from '../types';

export default function ExternalPanel({
  overview,
  onIncident,
}: {
  overview: Overview;
  onIncident: (id: string) => void;
}) {
  const { data: baselines, refresh } = usePolling<Baseline[]>('/api/baselines');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const baseline = baselines?.[0];
  async function capture() {
    setBusy(true);
    setError(null);
    try {
      await api('/api/baselines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Application healthy baseline',
          start: overview.now - 30,
          end: overview.now,
          services: overview.services.map((s) => s.service),
        }),
      });
      refresh();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Could not capture baseline');
    } finally {
      setBusy(false);
    }
  }
  async function analyse() {
    if (!baseline) return;
    setBusy(true);
    setError(null);
    try {
      const incident = await api<Incident>('/api/analyses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseline_id: baseline.id,
          title: 'Application observation',
          start: baseline.end,
          end: Date.now() / 1000,
        }),
      });
      onIncident(incident.id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Could not analyse window');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel experiment-panel">
      <div className="panel-heading">
        <span className="small-icon">
          <Radio size={18} />
        </span>
        <h2>Connected application</h2>
      </div>
      <p className="section-description">
        Standard OpenTelemetry traces from your own application. No demo faults are active.
      </p>
      <div className="scenario-description">
        <span className="badge success">OTLP / HTTP protobuf</span>
        <p>Export traces to:</p>
        <code className="collector-address">http://127.0.0.1:8100/v1/traces</code>
        <p>
          Services observed:{' '}
          <strong>{overview.services.map((s) => s.service).join(', ') || 'Waiting for traffic'}</strong>
        </p>
      </div>
      <div className="experiment-steps">
        <span>
          <b>01</b> Send healthy application traffic
        </span>
        <span>
          <b>02</b> Capture the last 30 seconds
        </span>
        <span>
          <b>03</b> Observe new traffic and analyse
        </span>
      </div>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <button
        className="button secondary full"
        disabled={busy || !overview.services.length}
        onClick={() => void capture()}
      >
        {busy ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />}Capture healthy baseline
      </button>
      <p className="microcopy">Only capture while your application is healthy.</p>
      <div className="scenario-description">
        <p>Active baseline: {baseline?.name ?? 'None captured'}</p>
      </div>
      <button className="button primary full" disabled={busy || !baseline} onClick={() => void analyse()}>
        <Activity size={15} /> Analyse since baseline <ArrowRight size={15} />
      </button>
      <p className="microcopy">
        Needs 5+ new requests per expected service. This action does not inject failures.
      </p>
    </section>
  );
}
