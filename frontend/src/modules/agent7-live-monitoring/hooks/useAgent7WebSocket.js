/**
 * Agent 7 Live Monitoring — SSE hook
 *
 * Connects to the Verdict backend at
 *   GET /agent7/stream/{scenarioId}
 * and streams MonitoringSnapshot frames via Server-Sent Events.
 *
 * Returns:
 *   { snapshot, history, connected, error, reconnect }
 */

import { useCallback, useEffect, useRef, useState } from "react";

const HISTORY_CAP = 200;

function deriveMetrics(probe_results = []) {
  const total = probe_results.length;
  const bad = probe_results.filter(
    (p) => p.status === "unhealthy" || p.status === "degraded",
  ).length;
  const latencies = probe_results
    .map((p) => p.response_time_ms)
    .filter(Boolean);
  return {
    error_rate_percent: total > 0 ? Math.round((bad / total) * 100) : 0,
    p99_latency_ms:
      latencies.length > 0 ? Math.round(Math.max(...latencies)) : null,
    active_instances: probe_results.filter((p) => p.status === "healthy").length,
  };
}

export function useAgent7WebSocket(scenarioId, options = {}) {
  const { autoConnect = true, reconnect: shouldReconnect = true } = options;

  const [snapshot, setSnapshot] = useState(null);
  const [history, setHistory] = useState([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);

  const sourceRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const closedByUser = useRef(false);

  const connect = useCallback(() => {
    if (!scenarioId) return;
    closedByUser.current = false;

    const es = new EventSource(
      `/api/agent7/stream/${encodeURIComponent(scenarioId)}`,
    );
    sourceRef.current = es;

    es.onopen = () => {
      setConnected(true);
      setError(null);
    };

    es.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data);
        if (frame.error) {
          setError(frame.error);
          return;
        }
        if (frame.type === "snapshot") {
          const s = { ...frame, ...deriveMetrics(frame.probe_results) };
          setSnapshot(s);
          setHistory((prev) => {
            const next = [...prev, s];
            return next.length > HISTORY_CAP ? next.slice(-HISTORY_CAP) : next;
          });
        }
      } catch {
        // ignore malformed frames
      }
    };

    es.onerror = () => {
      setConnected(false);
      es.close();
      sourceRef.current = null;
      if (shouldReconnect && !closedByUser.current) {
        reconnectTimerRef.current = window.setTimeout(connect, 2000);
      }
    };
  }, [scenarioId, shouldReconnect]);

  const reconnect = useCallback(() => {
    closedByUser.current = true;
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
    clearTimeout(reconnectTimerRef.current);
    connect();
  }, [connect]);

  useEffect(() => {
    if (!autoConnect || !scenarioId) return;
    connect();
    return () => {
      closedByUser.current = true;
      clearTimeout(reconnectTimerRef.current);
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, [autoConnect, scenarioId, connect]);

  return { snapshot, history, connected, error, reconnect };
}
