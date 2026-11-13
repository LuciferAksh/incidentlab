import { useState } from 'react';
import type { Span } from '../types';
import { ms, serviceColor } from '../format';
import { usePolling } from '../api';
import Dialog from './Dialog';
import Empty from './Empty';

export default function TraceDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, error } = usePolling<Span[]>(`/api/traces/${id}`, false, 5000);
  const [expanded, setExpanded] = useState<string | null>(null);
  const start = data?.length ? Math.min(...data.map((s) => s.start_ns)) : 0;
  const duration = data?.length ? Math.max(1, Math.max(...data.map((s) => s.end_ns)) - start) : 1;
  function depth(span: Span) {
    let n = 0;
    let parent = span.parent_id;
    const seen = new Set<string>();
    while (parent && !seen.has(parent) && n < 12) {
      seen.add(parent);
      const found = data?.find((s) => s.span_id === parent);
      if (!found) break;
      n++;
      parent = found.parent_id;
    }
    return n;
  }
  return (
    <Dialog title="Trace waterfall" onClose={onClose}>
      <p className="mono trace-id">{id}</p>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {!data ? (
        <Empty title="Loading trace">Fetching collected spansâ€¦</Empty>
      ) : (
        <>
          <div className="trace-summary">
            <span>{data.length} spans</span>
            <span>{ms(duration / 1e6)} total</span>
            <span>{new Set(data.map((s) => s.service)).size} services</span>
          </div>
          <div className="waterfall">
            {data.map((span) => (
              <div key={span.span_id}>
                <button
                  className="waterfall-row"
                  onClick={() => setExpanded(expanded === span.span_id ? null : span.span_id)}
                >
                  <span className="span-name" style={{ paddingLeft: depth(span) * 14 }}>
                    <span className="dot" style={{ background: serviceColor[span.service] ?? '#777' }} />
                    <span>
                      <strong>{span.service}</strong>
                      <small>{span.name}</small>
                    </span>
                  </span>
                  <span className="span-track">
                    <span
                      className={`span-bar ${span.error ? 'failed' : ''}`}
                      style={{
                        left: `${((span.start_ns - start) / duration) * 100}%`,
                        width: `${Math.max(0.6, ((span.end_ns - span.start_ns) / duration) * 100)}%`,
                        backgroundColor: span.error ? undefined : serviceColor[span.service],
                      }}
                    />
                  </span>
                  <span className={span.error ? 'orange-text' : ''}>{ms(span.duration_ms)}</span>
                </button>
                {expanded === span.span_id && (
                  <div className="span-details">
                    <h4>Attributes</h4>
                    <pre>{JSON.stringify(span.attributes, null, 2)}</pre>
                    {span.events.length > 0 && (
                      <>
                        <h4>Span events</h4>
                        <pre>{JSON.stringify(span.events, null, 2)}</pre>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          <p className="microcopy">
            Select a span to inspect attributes and events. Timing is measured by the service processes.
          </p>
        </>
      )}
    </Dialog>
  );
}
