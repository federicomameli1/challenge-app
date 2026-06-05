/**
 * Agent 7 Live Monitoring — WebSocket hook
 *
 * Connects to the Agent 7 backend at
 *   WS <apiBase>/api/agent7/ws/{scenarioId}
 * and streams MonitoringSnapshot frames.
 *
 * Returns:
 *   { snapshot, history, connected, error, reconnect }
 */

import { useCallback, useEffect, useRef, useState } from "react";

const DEFAULT_API_BASE =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_AGENT7_API_BASE) ||
  "http://127.0.0.1:8001";

const HISTORY_CAP = 200;

function apiToWs(apiBase) {
  return String(apiBase).replace(/^http/i, "ws");
}

export function useAgent7WebSocket(scenarioId, options = {}) {
  const {
    apiBase = DEFAULT_API_BASE,
    autoConnect = true,
    reconnect: shouldReconnect = true,
  } = options;

  const [snapshot, setSnapshot] = useState(null);
  const [history, setHistory] = useState([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const closedByUser = useRef(false);

  const buildUrl = useCallback(
    (sid) => `${apiToWs(apiBase)}/api/agent7/ws/${encodeURIComponent(sid)}`,
    [apiBase],
  );

  const connect = useCallback(() => {
    if (!scenarioId) return;
    closedByUser.current = false;
    try {
      const ws = new WebSocket(buildUrl(scenarioId));
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setError(null);
      };

      ws.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data);
          if (frame.type === "snapshot" && frame.data) {
            const s = frame.data;
            setSnapshot(s);
            setHistory((prev) => {
              const next = [...prev, s];
              return next.length > HISTORY_CAP ? next.slice(-HISTORY_CAP) : next;
            });
          }
        } catch {
          // Ignore malformed frames.
        }
      };

      ws.onerror = () => {
        setError("WebSocket error");
      };

      ws.onclose = () => {
        setConnected(false);
        if (shouldReconnect && !closedByUser.current) {
          reconnectTimerRef.current = window.setTimeout(connect, 2000);
        }
      };
    } catch (e) {
      setError(String(e?.message ?? e));
    }
  }, [scenarioId, buildUrl, shouldReconnect]);

  const reconnect = useCallback(() => {
    if (wsRef.current) {
      closedByUser.current = true;
      wsRef.current.close();
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    connect();
  }, [connect]);

  useEffect(() => {
    if (!autoConnect || !scenarioId) return;
    connect();
    return () => {
      closedByUser.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [autoConnect, scenarioId, connect]);

  return { snapshot, history, connected, error, reconnect };
}
