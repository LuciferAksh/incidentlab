import { useEffect, useState } from 'react';
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  FlaskConical,
  Gauge,
  GitBranch,
  Layers3,
  LayoutDashboard,
  LoaderCircle,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Server,
  ShieldCheck,
  TriangleAlert,
  X,
  Zap,
} from 'lucide-react';
import { api, usePolling } from './api';
import type { Overview, Scenario } from './types';
import { ms, percent } from './format';
import Chart from './components/Chart';
import ServiceMap from './components/ServiceMap';
import IncidentList from './components/IncidentList';
import ExperimentPanel from './components/ExperimentPanel';
import TraceExplorer from './components/TraceExplorer';
import Evaluation from './components/Evaluation';
import Architecture from './components/Architecture';
import Metric from './components/Metric';
import TraceDetail from './components/TraceDetail';
import IncidentDetail from './components/IncidentDetail';

type Tab = 'Overview' | 'Trace explorer' | 'Experiments' | 'Evaluation' | 'Architecture';
const nav = [
  { title: 'Overview', icon: LayoutDashboard },
  { title: 'Trace explorer', icon: GitBranch },
  { title: 'Experiments', icon: FlaskConical },
  { title: 'Evaluation', icon: ShieldCheck },
  { title: 'Architecture', icon: Layers3 },
] as const;

export default function App() {
  const [tab, setTab] = useState<Tab>('Overview');
  const [paused, setPaused] = useState(false);
  const { data: overview, error, refresh } = usePolling<Overview>('/api/overview', paused);
  const { data: scenarios } = usePolling<Scenario[]>('/api/scenarios', false, 60000);
  const [scenario, setScenario] = useState('inventory-latency');
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [pendingRun, setPendingRun] = useState<string | null>(null);
  const busy = submitting || !overview || !['idle', 'error'].includes(overview.lab.phase);
  useEffect(() => {
    if (pendingRun && overview?.incidents.some((i) => i.id === pendingRun)) {
      setIncidentId(pendingRun);
      setPendingRun(null);
    }
  }, [overview, pendingRun]);
  async function run() {
    setActionError(null);
    setSubmitting(true);
    setPaused(false);
    try {
      const result = await api<{ run_id: string }>('/api/experiments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario }),
      });
      setPendingRun(result.run_id);
      refresh();
    } catch (exc) {
      setActionError(exc instanceof Error ? exc.message : 'Experiment could not start');
    } finally {
      setSubmitting(false);
    }
  }
  const checkout = overview?.services.find((s) => s.service === 'checkout');
  const anomalous = overview?.diagnosis.status === 'incident';
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="IncidentLab home">
          <span>
            <Activity size={23} />
          </span>
          incident<span className="brand-light">lab</span>
          <sup>β</sup>
        </a>
        <button className="workspace" onClick={() => setTab('Architecture')}>
          <span className="workspace-avatar">IL</span>
          <span>
            Engineering lab<small>Local workspace</small>
          </span>
          <ChevronDown size={14} />
        </button>
        <p className="nav-label">OBSERVABILITY</p>
        <nav aria-label="Main navigation">
          {nav.map(({ title, icon: Icon }) => (
            <button
              key={title}
              className={tab === title ? 'active' : ''}
              aria-current={tab === title ? 'page' : undefined}
              onClick={() => setTab(title)}
            >
              <Icon size={18} />
              <span>{title}</span>
              {title === 'Experiments' && <span className="nav-count">5</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="lab-note">
            <span className="note-icon">
              <FlaskConical size={19} />
            </span>
            <strong>
              A little chaos.
              <br />A lot of clarity.
            </strong>
            <p>A real service lab for understanding distributed failures.</p>
            <button onClick={() => setTab('Architecture')}>
              How it works <ArrowUpRight size={14} />
            </button>
          </div>
          <a href="/docs" target="_blank" rel="noreferrer">
            <BookOpen size={16} /> API reference <ArrowUpRight size={13} />
          </a>
          <div className="sidebar-profile">
            <span>AM</span>
            <div>
              IncidentLab<small>Development environment</small>
            </div>
            <span className="dot green" />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={13} />
            <span>incidentlab</span>
            <ChevronRight size={13} />
            <strong>{tab}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-chip">
              <span className="dot green" /> Local environment
            </span>
            <button
              className="icon-button"
              aria-label="About IncidentLab"
              onClick={() => setTab('Architecture')}
            >
              <CircleHelp size={19} />
            </button>
            <span className="avatar">IL</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="dot green" /> YOUR SYSTEM, UNDERSTOOD
              </div>
              <h1>{tab === 'Overview' ? 'System overview' : tab}</h1>
              <p>
                {
                  {
                    Overview: 'Every signal tells a story. Follow the evidence.',
                    'Trace explorer': 'Follow a request across every service boundary.',
                    Experiments: 'Reproduce a failure. Inspect the impact. Verify the diagnosis.',
                    Evaluation: 'Measure what works, and make the limitations visible.',
                    Architecture: 'Understand the system behind the signals.',
                  }[tab]
                }
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="button secondary"
                onClick={() => {
                  refresh();
                  setPaused(false);
                }}
              >
                <RefreshCw size={14} /> Refresh
              </button>
              <button
                className="button primary"
                onClick={() => {
                  setTab('Experiments');
                }}
              >
                <FlaskConical size={15} /> New experiment
              </button>
            </div>
          </div>
          {(error || actionError) && (
            <div className="error-banner" role="alert">
              <TriangleAlert size={17} />
              <span>
                {actionError || `API connection interrupted: ${error}. Reconnecting automatically.`}
              </span>
              {actionError && (
                <button
                  className="icon-button"
                  aria-label="Dismiss error"
                  onClick={() => setActionError(null)}
                >
                  <X size={16} />
                </button>
              )}
            </div>
          )}
          {overview && overview.lab.phase !== 'idle' && (
            <div className={`run-banner ${overview.lab.phase === 'error' ? 'error' : ''}`} role="status">
              {overview.lab.phase === 'error' ? (
                <TriangleAlert size={17} />
              ) : (
                <LoaderCircle size={17} className="spin" />
              )}
              <strong>
                {overview.lab.phase === 'error'
                  ? 'Lab needs attention'
                  : overview.lab.phase === 'warming'
                    ? 'Preparing your lab'
                    : 'Experiment running'}
              </strong>
              <span>{overview.lab.message}</span>
            </div>
          )}
          {tab === 'Overview' && (
            <>
              <div className="overview-toolbar">
                <span className={`badge ${error ? 'warning' : 'success'}`}>
                  <span className={`dot ${error ? 'orange' : 'green'}`} />
                  {error
                    ? 'Reconnecting'
                    : paused
                      ? 'Updates paused'
                      : overview
                        ? 'Live telemetry'
                        : 'Connecting'}
                </span>
                <div>
                  <Clock3 size={14} />
                  <span>Last 60 seconds</span>
                  <span className="toolbar-divider" />
                  <button
                    aria-label={paused ? 'Resume live updates' : 'Pause live updates'}
                    onClick={() => setPaused(!paused)}
                  >
                    {paused ? <Play size={13} /> : <Pause size={13} />}
                    {paused ? 'Resume' : 'Pause'}
                  </button>
                </div>
              </div>
              <div className="metrics">
                <Metric
                  title="Observed requests"
                  value={overview ? String(overview.request_count) : '—'}
                  icon={<Activity size={17} />}
                  footer="Checkout requests · last 60 sec"
                />
                <Metric
                  title="Request latency"
                  value={checkout ? ms(checkout.p95_ms) : '—'}
                  icon={<Gauge size={17} />}
                  footer="95th percentile · checkout"
                  warning={!!checkout && checkout.p95_ms > 200}
                />
                <Metric
                  title="Error rate"
                  value={overview ? percent(overview.error_rate) : '—'}
                  icon={<TriangleAlert size={17} />}
                  footer="Failed checkout requests"
                  warning={(overview?.error_rate ?? 0) > 0.1}
                />
                <Metric
                  title="Services observed"
                  value={overview ? `${overview.services.length} / 3` : '—'}
                  icon={<Server size={17} />}
                  footer={`${overview?.span_count ?? 0} collected spans · last 60 sec`}
                />
              </div>
              <div className="overview-grid">
                <div className="overview-primary">
                  <section className="panel">
                    <div className="panel-heading spread">
                      <div>
                        <h2>Request latency</h2>
                        <p>Checkout p95 · milliseconds</p>
                      </div>
                      <span className="legend">
                        <span className="dot green" /> checkout
                      </span>
                    </div>
                    <Chart overview={overview} />
                  </section>
                  <section className="panel">
                    <div className="panel-heading spread">
                      <h2>Service dependency map</h2>
                      <span className="badge neutral">3-service lab</span>
                    </div>
                    <ServiceMap overview={overview} />
                  </section>
                </div>
                <div className="overview-secondary">
                  <ExperimentPanel
                    scenarios={scenarios ?? []}
                    busy={busy}
                    selected={scenario}
                    onSelect={setScenario}
                    onRun={() => void run()}
                    compact
                  />
                  <div className={`signal-note ${anomalous ? 'has-anomaly' : ''}`}>
                    <span className="small-icon">
                      {anomalous ? <TriangleAlert size={17} /> : <Radio size={17} />}
                    </span>
                    <div>
                      <strong>
                        {anomalous ? 'A signal worth investigating' : 'Signals, without the guesswork'}
                      </strong>
                      <p>
                        {anomalous
                          ? `Leading suspect: ${overview?.diagnosis.suspects[0]?.service}. Inspect a saved experiment for a clean observation window.`
                          : 'Diagnosis uses observed traces. Fault labels are reserved for evaluation.'}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
              <section className="panel recent-incidents">
                <div className="panel-heading spread">
                  <div>
                    <h2>
                      Recent investigations <span className="count">{overview?.incidents.length ?? 0}</span>
                    </h2>
                    <p>Captured evidence from your controlled experiments</p>
                  </div>
                  <button className="text-link" onClick={() => setTab('Experiments')}>
                    View all <ArrowRight size={14} />
                  </button>
                </div>
                <IncidentList incidents={overview?.incidents.slice(0, 5) ?? []} onSelect={setIncidentId} />
              </section>
            </>
          )}
          {tab === 'Trace explorer' && <TraceExplorer onTrace={setTraceId} />}
          {tab === 'Experiments' && (
            <>
              <div className="experiment-page">
                <ExperimentPanel
                  scenarios={scenarios ?? []}
                  busy={busy}
                  selected={scenario}
                  onSelect={setScenario}
                  onRun={() => void run()}
                />
                <section className="panel scenario-catalog">
                  <div className="panel-heading">
                    <h2>Choose your failure boundary</h2>
                  </div>
                  {scenarios?.map((s) => (
                    <button
                      className={`scenario-option ${scenario === s.id ? 'selected' : ''}`}
                      key={s.id}
                      onClick={() => setScenario(s.id)}
                      disabled={busy}
                    >
                      <span className="small-icon">
                        {s.id === 'healthy' ? <ShieldCheck size={18} /> : <Zap size={18} />}
                      </span>
                      <span>
                        <strong>{s.name}</strong>
                        <small>{s.description}</small>
                      </span>
                      {scenario === s.id && <Check size={18} />}
                    </button>
                  ))}
                </section>
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Investigation history</h2>
                </div>
                <IncidentList incidents={overview?.incidents ?? []} onSelect={setIncidentId} />
              </section>
            </>
          )}
          {tab === 'Evaluation' && <Evaluation onIncident={setIncidentId} />}
          {tab === 'Architecture' && <Architecture />}
          <footer>
            <span>
              <Activity size={13} /> IncidentLab <span className="footer-version">v0.1.0</span>
            </span>
            <span>Real traces. Reproducible failures. Explainable diagnosis.</span>
            <span className="footer-status">
              <span className={`dot ${error ? 'orange' : 'green'}`} />
              {error ? 'API disconnected' : overview ? 'Collector connected' : 'Connecting to collector'}
            </span>
          </footer>
        </main>
      </div>
      {incidentId && (
        <IncidentDetail
          key={incidentId}
          id={incidentId}
          onClose={() => setIncidentId(null)}
          onTrace={(id) => {
            setIncidentId(null);
            setTraceId(id);
          }}
        />
      )}
      {traceId && <TraceDetail key={traceId} id={traceId} onClose={() => setTraceId(null)} />}
    </div>
  );
}
