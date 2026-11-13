import { useEffect, useRef, useState } from 'react';

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`);
  }
  return response.json();
}

export function usePolling<T>(path: string, paused = false, interval = 2000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useRef<() => void>(() => {});
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | null = null;
    let generation = 0;
    async function poll() {
      const requestGeneration = ++generation;
      clearTimeout(timer);
      controller?.abort();
      controller = new AbortController();
      try {
        const result = await api<T>(path, { signal: controller.signal });
        if (!disposed && requestGeneration === generation) {
          setData(result);
          setError(null);
        }
      } catch (exc) {
        if (
          !disposed &&
          requestGeneration === generation &&
          exc instanceof Error &&
          exc.name !== 'AbortError'
        )
          setError(exc.message);
      } finally {
        if (!disposed && requestGeneration === generation && !paused) timer = setTimeout(poll, interval);
      }
    }
    refresh.current = () => {
      void poll();
    };
    if (!paused) void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [path, paused, interval]);
  return { data, error, refresh: () => refresh.current() };
}
