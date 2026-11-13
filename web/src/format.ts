export const time = (seconds: number) =>
  new Date(seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
export const percent = (value: number | null | undefined) =>
  value == null ? '—' : `${(value * 100).toFixed(1)}%`;
export const ms = (value: number) =>
  value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(0)} ms`;
export const serviceColor: Record<string, string> = {
  checkout: '#6b86c5',
  inventory: '#bc8b4b',
  payments: '#729b78',
};
