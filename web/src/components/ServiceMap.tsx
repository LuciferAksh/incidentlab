import { ArrowRight, GitBranch, Server, Workflow } from 'lucide-react';
import type { Overview } from '../types';
import { ms, serviceColor } from '../format';

export default function ServiceMap({ overview }: { overview: Overview | null }) {
  if (overview?.mode === 'external') {
    return (
      <div className="service-map">
        <div className="map-caption">
          <span className="dot blue" /> Observed application services
        </div>
        <div className="external-services">
          {overview.services.map((service) => (
            <div className="service-node leaf" key={service.service}>
              <span className="service-icon">
                <Server size={18} />
              </span>
              <div>
                <strong>{service.service}</strong>
                <small>
                  {ms(service.p95_ms)} p95 · {service.requests} requests
                </small>
              </div>
              <span className={`dot ${service.error_rate > 0.1 ? 'orange' : 'green'}`} />
            </div>
          ))}
        </div>
        {overview.topology.map((edge) => (
          <p className="external-edge" key={`${edge.source}-${edge.target}`}>
            {edge.source} → {edge.target} · {edge.calls} calls · {ms(edge.p95_ms)} p95
          </p>
        ))}
        <div className="map-footer">
          <GitBranch size={13} />{' '}
          {overview.topology.length
            ? 'Edges derived from parent spans'
            : 'No cross-service edge observed. A single Django app is one service.'}
        </div>
      </div>
    );
  }
  const nodes = ['checkout', 'inventory', 'payments'];
  return (
    <div className="service-map">
      <div className="map-caption">
        <span className="dot blue" /> Traced service dependency
      </div>
      <div className="map-flow">
        <div className="client-node">
          <Workflow size={18} />
          <span>
            Traffic
            <br />
            <small>generator</small>
          </span>
        </div>
        <ArrowRight className="map-arrow" size={20} />
        <div className="service-node checkout">
          <span className="service-icon" style={{ background: '#edf1fb', color: serviceColor.checkout }}>
            <Server size={20} />
          </span>
          <strong>checkout</strong>
          <small>HTTP entry point</small>
        </div>
        <div className="map-branch">
          <div />
          <div />
        </div>
        <div className="leaf-nodes">
          {nodes.slice(1).map((name) => {
            const metrics = overview?.services.find((s) => s.service === name);
            const anomalous = overview?.diagnosis.suspects.some((s) => s.service === name);
            return (
              <div key={name} className={`service-node leaf ${anomalous ? 'anomalous' : ''}`}>
                <span
                  className="service-icon"
                  style={{ color: serviceColor[name], background: `${serviceColor[name]}15` }}
                >
                  <Server size={17} />
                </span>
                <div>
                  <strong>{name}</strong>
                  <small>{metrics ? `${ms(metrics.p95_ms)} p95` : 'Awaiting traces'}</small>
                </div>
                <span className={`dot ${anomalous ? 'orange' : metrics ? 'green' : 'muted'}`} />
              </div>
            );
          })}
        </div>
      </div>
      <div className="map-footer">
        <GitBranch size={13} /> Edges discovered from cross-service parent spans{' '}
        <span>{overview?.topology.length ?? 0} edges</span>
      </div>
    </div>
  );
}
