import { useState } from 'react';
import { ArrowUpRight, Search } from 'lucide-react';
import type { TraceRow } from '../types';
import { ms, time } from '../format';
import { usePolling } from '../api';
import Empty from './Empty';

export default function TraceExplorer({ onTrace }: { onTrace: (id: string) => void }) {
  const { data, error } = usePolling<TraceRow[]>('/api/traces');
  const [query, setQuery] = useState('');
  const [errorsOnly, setErrorsOnly] = useState(false);
  const filtered = (data ?? []).filter(
    (t) => `${t.trace_id} ${t.service} ${t.name}`.includes(query.toLowerCase()) && (!errorsOnly || t.error),
  );
  return (
    <section className="panel">
      <div className="panel-heading spread">
        <h2>Recent request traces</h2>
        <span className="badge neutral">Latest 60 Â· 1 hour</span>
      </div>
      <div className="trace-toolbar">
        <label className="search-input">
          <Search size={16} />
          <input
            aria-label="Search traces"
            placeholder="Search trace ID or serviceâ€¦"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} />{' '}
          Errors only
        </label>
      </div>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {!filtered.length ? (
        <Empty title="No matching traces">Live requests will appear here. Try clearing your filters.</Empty>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Trace ID</th>
                <th>Entry point</th>
                <th>Duration</th>
                <th>Status</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr key={t.trace_id}>
                  <td>
                    <button className="text-link mono" onClick={() => onTrace(t.trace_id)}>
                      {t.trace_id.slice(0, 16)}â€¦ <ArrowUpRight size={13} />
                    </button>
                  </td>
                  <td>
                    {t.service}
                    <small>{t.name}</small>
                  </td>
                  <td>{ms(t.duration_ms)}</td>
                  <td>
                    <span className={`badge ${t.error ? 'warning' : 'success'}`}>
                      {t.error ? 'Error' : 'OK'}
                    </span>
                  </td>
                  <td>{time(t.start_ns / 1e9)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
