import { ArrowUpRight, ShieldCheck } from 'lucide-react';
import type { Incident } from '../types';
import { time } from '../format';
import { usePolling } from '../api';
import Dialog from './Dialog';
import Empty from './Empty';

export default function IncidentDetail({
  id,
  onClose,
  onTrace,
}: {
  id: string;
  onClose: () => void;
  onTrace: (id: string) => void;
}) {
  const { data: incident, error } = usePolling<Incident>(`/api/incidents/${id}`, false, 5000);
  return (
    <Dialog title={incident?.title ?? 'Incident investigation'} onClose={onClose}>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {!incident ? (
        <Empty title="Loading evidence">Fetching the saved experiment…</Empty>
      ) : (
        <>
          <div className="trace-summary">
            <span>{incident.trace_count} observed traces</span>
            <span>{incident.duration_seconds}s window</span>
            <span className={`badge ${incident.top1_correct ? 'success' : 'warning'}`}>
              {incident.source === 'external'
                ? 'External telemetry'
                : incident.top1_correct
                  ? 'Ground truth matched'
                  : 'Needs investigation'}
            </span>
          </div>
          <h3 className="subheading">Ranked suspects</h3>
          {!incident.diagnosis.suspects.length && (
            <div className="callout">
              <ShieldCheck size={22} />
              <p>
                {incident.diagnosis.status === 'healthy'
                  ? 'No anomaly detected against the healthy baseline.'
                  : 'Insufficient telemetry to make a diagnosis.'}
              </p>
            </div>
          )}
          {incident.diagnosis.suspects.map((s, i) => (
            <article className="suspect" key={s.service}>
              <div className="spread">
                <h3>
                  <span className="rank">{i + 1}</span>
                  {s.service}
                </h3>
                <span className="badge neutral">Evidence score {s.score}/100</span>
              </div>
              <ul>
                {s.evidence.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
              <p>{s.recommendation}</p>
              <button className="text-link" onClick={() => onTrace(s.trace_id)}>
                Inspect supporting trace <ArrowUpRight size={14} />
              </button>
            </article>
          ))}
          <h3 className="subheading">Experiment timeline</h3>
          <ol className="timeline">
            {incident.timeline?.map((e, i) => (
              <li key={i}>
                <time>{time(e.at)}</time>
                <span>{e.message}</span>
              </li>
            ))}
          </ol>
          <div className="evaluation-note">
            {incident.source === 'external' ? (
              <>
                Analysis of a separately instrumented application. No fault label was supplied to the
                diagnosis engine. Confirm the candidate using its supporting trace.
              </>
            ) : (
              <>
                <strong>Evaluation only:</strong> injected target was{' '}
                <code>{incident.ground_truth ?? 'none (healthy control)'}</code>. This label was not passed to
                the diagnosis engine.
              </>
            )}
          </div>
          <p className="microcopy">{incident.diagnosis.caveats.join(' ')}</p>
        </>
      )}
    </Dialog>
  );
}
