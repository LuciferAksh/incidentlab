import { ArrowRight, ChevronDown, FlaskConical, LoaderCircle, Play, ShieldCheck } from 'lucide-react';
import type { Scenario } from '../types';

export default function ExperimentPanel({
  scenarios,
  busy,
  selected,
  onSelect,
  onRun,
  compact = false,
}: {
  scenarios: Scenario[];
  busy: boolean;
  selected: string;
  onSelect: (id: string) => void;
  onRun: () => void;
  compact?: boolean;
}) {
  const scenario = scenarios.find((s) => s.id === selected);
  return (
    <section className={`panel experiment-panel ${compact ? 'compact' : ''}`}>
      <div className="panel-heading">
        <span className="small-icon">
          <FlaskConical size={18} />
        </span>
        <h2>Break it. Understand it.</h2>
      </div>
      <p className="section-description">
        Introduce a controlled failure. Follow its impact through the system.
      </p>
      <label className="field-label" htmlFor={compact ? 'scenario-compact' : 'scenario'}>
        FAULT SCENARIO
      </label>
      <div className="select-wrap">
        <select
          id={compact ? 'scenario-compact' : 'scenario'}
          value={selected}
          onChange={(e) => onSelect(e.target.value)}
          disabled={busy || !scenarios.length}
        >
          {scenarios.length ? (
            scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))
          ) : (
            <option>Loading scenarios…</option>
          )}
        </select>
        <ChevronDown size={15} />
      </div>
      <div className="scenario-description">
        <span className="badge neutral">{scenario?.category ?? 'Loading'}</span>
        <p>{scenario?.description ?? 'Connecting to the service lab.'}</p>
      </div>
      <div className="experiment-steps">
        <span>
          <b>01</b> Measure healthy baseline
        </span>
        <span>
          <b>02</b> Inject & observe failure
        </span>
        <span>
          <b>03</b> Rank evidence & recover
        </span>
      </div>
      <button className="button primary full" onClick={onRun} disabled={busy || !scenario}>
        {busy ? <LoaderCircle size={16} className="spin" /> : <Play size={15} fill="currentColor" />}{' '}
        {busy ? 'Experiment in progress' : 'Run experiment'}
        {!busy && <ArrowRight size={16} />}
      </button>
      <p className="microcopy">
        <ShieldCheck size={13} /> Faults are removed after every experiment.
      </p>
    </section>
  );
}
