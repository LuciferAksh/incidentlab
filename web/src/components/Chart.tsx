import type { Overview } from '../types';

export default function Chart({ overview }: { overview: Overview | null }) {
  const series = overview?.series ?? [];
  const ceiling = Math.max(100, ...series.map((p) => p.p95_ms)) * 1.15;
  const coordinates = series.map((p, i) => [44 + i * 57, 154 - (p.p95_ms / ceiling) * 126]);
  const path = coordinates.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${y}`).join(' ');
  return (
    <div
      className="chart"
      role="img"
      aria-label="Checkout p95 latency over the last 60 seconds in five-second buckets"
    >
      <svg viewBox="0 0 700 190" preserveAspectRatio="none">
        <defs>
          <linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#c2d5bc" stopOpacity=".6" />
            <stop offset="100%" stopColor="#c2d5bc" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((i) => (
          <g key={i}>
            <line x1="44" x2="682" y1={28 + i * 42} y2={28 + i * 42} stroke="#ecefea" strokeDasharray="3 4" />
            <text x="0" y={32 + i * 42} className="chart-label">
              {Math.round(ceiling * (1 - i / 3))}
            </text>
          </g>
        ))}
        {path && (
          <>
            <path d={`${path} L${coordinates.at(-1)![0]},154 L44,154 Z`} fill="url(#chart-fill)" />
            <path d={path} fill="none" stroke="#6a8f65" strokeWidth="2.5" strokeLinejoin="round" />
            {coordinates.map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r="3" fill="#6a8f65">
                <title>
                  {series[i].p95_ms} ms · {series[i].requests} requests
                </title>
              </circle>
            ))}
          </>
        )}
        <text x="44" y="182" className="chart-label">
          60 sec ago
        </text>
        <text x="330" y="182" className="chart-label">
          30 sec ago
        </text>
        <text x="651" y="182" className="chart-label">
          Now
        </text>
      </svg>
    </div>
  );
}
