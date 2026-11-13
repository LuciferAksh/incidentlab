import { ArrowDown, ArrowUpRight, Code2, GitBranch, ShieldCheck, Terminal } from 'lucide-react';

export default function Architecture() {
  return (
    <>
      <section className="panel architecture">
        <div className="panel-heading">
          <h2>Small system. Real failure boundaries.</h2>
          <span className="badge success">No API keys required</span>
        </div>
        <p>
          Three independent HTTP services send OpenTelemetry spans to a local collector. The diagnosis engine
          reads observed spans; the experiment controller keeps injected fault labels separate.
        </p>
        <div className="architecture-flow">
          {[
            'React dashboard',
            'FastAPI control plane',
            'OTLP trace collector',
            'SQLite WAL store',
            'Evidence ranking',
          ].map((name, i) => (
            <div key={name}>
              <span>{String(i + 1).padStart(2, '0')}</span>
              <strong>{name}</strong>
              {i < 4 && <ArrowDown size={18} />}
            </div>
          ))}
        </div>
        <div className="architecture-grid">
          <article>
            <Code2 size={22} />
            <h3>Explainable diagnosis</h3>
            <p>
              Compare p95 latency and error rates with a healthy baseline. Rank local evidence using exclusive
              time, slow internal operations, and failures without failing descendants.
            </p>
          </article>
          <article>
            <GitBranch size={22} />
            <h3>Distributed tracing</h3>
            <p>
              W3C trace context crosses service boundaries. Inspect parent-child relationships, operation
              timing, attributes, and structured span events.
            </p>
          </article>
          <article>
            <ShieldCheck size={22} />
            <h3>Honest limitations</h3>
            <p>
              Single-machine lab, trace-derived metrics, heuristic scores, no causal proof. Span coverage and
              clock skew affect results. This local control plane is not a multi-tenant production service.
            </p>
          </article>
        </div>
      </section>
      <div className="callout">
        <Terminal size={20} />
        <div>
          <strong>Built to be inspected.</strong>
          <p>
            Use the repository's tests and evaluation script to reproduce the results. The API reference is
            available at{' '}
            <a href="/docs" target="_blank" rel="noreferrer">
              /docs <ArrowUpRight size={12} />
            </a>
            .
          </p>
        </div>
      </div>
    </>
  );
}
