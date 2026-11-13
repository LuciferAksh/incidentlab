import { ArrowUpRight, Check, FlaskConical, Zap } from 'lucide-react';
import type { Incident } from '../types';
import { time } from '../format';
import Empty from './Empty';

export default function IncidentList({
  incidents,
  onSelect,
}: {
  incidents: Incident[];
  onSelect: (id: string) => void;
}) {
  if (!incidents.length)
    return (
      <Empty icon={<FlaskConical size={26} />} title="Your first investigation starts here">
        Run an experiment to capture an incident, rank suspects, and inspect the evidence.
      </Empty>
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Experiment</th>
            <th>Top suspect</th>
            <th>Evaluation</th>
            <th>Started</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {incidents.map((i) => (
            <tr key={i.id}>
              <td>
                <button className="table-title" onClick={() => onSelect(i.id)}>
                  <span className={`incident-symbol ${i.diagnosis.status === 'healthy' ? 'good' : ''}`}>
                    {i.diagnosis.status === 'healthy' ? <Check size={15} /> : <Zap size={15} />}
                  </span>
                  <span>
                    {i.title}
                    <small>{i.id}</small>
                  </span>
                </button>
              </td>
              <td>
                <code>
                  {i.diagnosis.suspects[0]?.service ??
                    (i.diagnosis.status === 'healthy' ? 'No anomaly' : 'Insufficient data')}
                </code>
              </td>
              <td>
                <span className={`badge ${i.top1_correct ? 'success' : 'warning'}`}>
                  {i.top1_correct ? 'Target matched' : 'Review result'}
                </span>
              </td>
              <td className="muted-text">{time(i.created_at)}</td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Inspect ${i.title}`}
                  onClick={() => onSelect(i.id)}
                >
                  <ArrowUpRight size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
