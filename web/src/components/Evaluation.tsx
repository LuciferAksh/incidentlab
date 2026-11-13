import { Download, FlaskConical, Gauge, ShieldCheck } from 'lucide-react';
import type { Report } from '../types';
import { percent } from '../format';
import { api, usePolling } from '../api';
import IncidentList from './IncidentList';
import Metric from './Metric';

export default function Evaluation({ onIncident }: { onIncident: (id: string) => void }) {
  const { data: report, error } = usePolling<Report>('/api/report', false, 3000);
  async function download() {
    try {
      const result = await api<Report>('/api/report');
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }),
      );
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'incidentlab-evaluation.json';
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      alert('Could not download the report. Check the API connection and try again.');
    }
  }
  return (
    <>
      <div className="callout">
        <ShieldCheck size={21} />
        <div>
          <strong>Evidence before claims.</strong>
          <p>
            Ground truth is attached after diagnosis. These results measure local injected scenarios, not
            production accuracy.
          </p>
        </div>
        <button className="button secondary" onClick={() => void download()}>
          <Download size={15} /> Export JSON
        </button>
      </div>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <div className="metrics three">
        <Metric
          title="Completed runs"
          value={String(report?.runs ?? 0)}
          icon={<FlaskConical size={17} />}
          footer="Persisted experiment results"
        />
        <Metric
          title="Top-1 match"
          value={percent(report?.top1_accuracy)}
          icon={<Gauge size={17} />}
          footer={`${report?.fault_runs ?? 0} fault runs · heuristic ranking`}
        />
        <Metric
          title="Control false positives"
          value={percent(report?.control_false_positive_rate)}
          icon={<ShieldCheck size={17} />}
          footer={`${report?.control_runs ?? 0} healthy control runs`}
        />
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Experiment ledger</h2>
        </div>
        <IncidentList incidents={report?.incidents ?? []} onSelect={onIncident} />
      </section>
    </>
  );
}
