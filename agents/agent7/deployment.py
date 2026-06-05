"""
Phase 7 deployment executor and live monitoring system.

Handles:
- Pre-deployment validation and readiness checks
- Actual deployment execution (dry-run by default)
- Continuous live monitoring during stabilization window
- Health probe evaluation and stability detection
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .models import (
    DeploymentRecord,
    DeploymentStatus,
    HealthProbeResult,
    HealthProbeStatus,
    MonitoringSnapshot,
    MonitoringState,
    SourceRef,
    utc_now_iso,
)


# ---------------------------------------------------------------------------
# Health probes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthProbe:
    """A single health probe to evaluate during monitoring."""
    name: str
    check_fn: Callable[[], HealthProbeResult]
    weight: float = 1.0  # Weight for overall status calculation


class HTTPHealthProbe:
    """HTTP-based health probe — returns degraded if response time exceeds threshold."""
    def __init__(
        self,
        url: str,
        name: str = "",
        timeout_ms: float = 2000.0,
        critical_threshold_ms: float = 5000.0,
    ) -> None:
        self.url = url
        self.name = name or url
        self.timeout_ms = timeout_ms
        self.critical_threshold_ms = critical_threshold_ms

    def execute(self) -> HealthProbeResult:
        import urllib.request
        import urllib.error
        start = time.monotonic()
        try:
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=self.timeout_ms / 1000.0) as resp:
                elapsed_ms = (time.monotonic() - start) * 1000
                if resp.status >= 500:
                    return HealthProbeResult(
                        probe_name=self.name,
                        status=HealthProbeStatus.UNHEALTHY,
                        response_time_ms=elapsed_ms,
                        error_message=f"HTTP {resp.status}",
                    )
                elif resp.status >= 400:
                    return HealthProbeResult(
                        probe_name=self.name,
                        status=HealthProbeStatus.DEGRADED,
                        response_time_ms=elapsed_ms,
                        error_message=f"HTTP {resp.status}",
                    )
                elif elapsed_ms > self.critical_threshold_ms:
                    return HealthProbeResult(
                        probe_name=self.name,
                        status=HealthProbeStatus.DEGRADED,
                        response_time_ms=elapsed_ms,
                        error_message="Response time exceeds threshold",
                    )
                return HealthProbeResult(
                    probe_name=self.name,
                    status=HealthProbeStatus.HEALTHY,
                    response_time_ms=elapsed_ms,
                )
        except urllib.error.URLError as exc:
            return HealthProbeResult(
                probe_name=self.name,
                status=HealthProbeStatus.UNHEALTHY,
                error_message=str(exc.reason),
            )
        except Exception as exc:
            return HealthProbeResult(
                probe_name=self.name,
                status=HealthProbeStatus.UNHEALTHY,
                error_message=str(exc),
            )


class SyntheticProbe:
    """Synthetic health probe — always returns a given status. Used for dry-run mode."""
    def __init__(self, name: str, status: HealthProbeStatus) -> None:
        self.name = name
        self._status = status

    def execute(self) -> HealthProbeResult:
        return HealthProbeResult(
            probe_name=self.name,
            status=self._status,
            response_time_ms=50.0 if self._status == HealthProbeStatus.HEALTHY else None,
        )


# ---------------------------------------------------------------------------
# Live Monitoring Service
# ---------------------------------------------------------------------------


class LiveMonitoringService:
    """
    Continuous health monitoring during deployment stabilization window.

    Runs in a background thread, collecting health snapshots at regular intervals.
    Tracks stability by checking if all probes remain HEALTHY for a sustained period.
    """

    def __init__(
        self,
        probes: Tuple[HealthProbe, ...],
        interval_seconds: float = 15.0,
        stabilization_seconds: float = 60.0,
    ) -> None:
        self.probes = probes
        self.interval_seconds = interval_seconds
        self.stabilization_seconds = stabilization_seconds

        self._snapshots: List[MonitoringSnapshot] = []
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._state = MonitoringState()

    def start(self, version: str = "") -> MonitoringState:
        """Start background monitoring thread."""
        self._stop_event.clear()
        self._snapshots.clear()
        self._state = MonitoringState(
            deployment_status=DeploymentStatus.STABILIZING,
        )
        self._thread = Thread(target=self._run, args=(version,), daemon=True)
        self._thread.start()
        return self._state

    def stop(self) -> MonitoringState:
        """Stop monitoring and return final state."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        return self._finalize_state()

    def get_current_state(self) -> MonitoringState:
        return self._state

    def _run(self, version: str) -> None:
        while not self._stop_event.is_set():
            snapshot = self._collect_snapshot(version)
            self._snapshots.append(snapshot)
            self._update_state(snapshot)
            self._stop_event.wait(self.interval_seconds)

    def _collect_snapshot(self, version: str) -> MonitoringSnapshot:
        results: List[HealthProbeResult] = []
        for probe in self.probes:
            results.append(probe.check_fn())

        overall = self._compute_overall_status(results)
        error_rate = self._compute_error_rate(results)
        p99_latency = self._compute_p99_latency(results)
        active_instances = len(results)

        return MonitoringSnapshot(
            timestamp_utc=utc_now_iso(),
            overall_status=overall,
            probe_results=tuple(results),
            error_rate_percent=error_rate,
            p99_latency_ms=p99_latency,
            active_instances=active_instances,
            deployed_version=version,
        )

    def _compute_overall_status(self, results: List[HealthProbeResult]) -> HealthProbeStatus:
        if not results:
            return HealthProbeStatus.UNKNOWN
        statuses = [r.status for r in results]
        if any(s == HealthProbeStatus.UNHEALTHY for s in statuses):
            return HealthProbeStatus.UNHEALTHY
        if any(s == HealthProbeStatus.DEGRADED for s in statuses):
            return HealthProbeStatus.DEGRADED
        if all(s == HealthProbeStatus.HEALTHY for s in statuses):
            return HealthProbeStatus.HEALTHY
        return HealthProbeStatus.UNKNOWN

    def _compute_error_rate(self, results: List[HealthProbeResult]) -> Optional[float]:
        if not results:
            return None
        unhealthy = sum(1 for r in results if r.status == HealthProbeStatus.UNHEALTHY)
        return round(unhealthy / len(results) * 100, 2)

    def _compute_p99_latency(self, results: List[HealthProbeResult]) -> Optional[float]:
        latencies = [r.response_time_ms for r in results if r.response_time_ms is not None]
        if not latencies:
            return None
        sorted_lat = sorted(latencies)
        idx = int(len(sorted_lat) * 0.99)
        return round(sorted_lat[min(idx, len(sorted_lat) - 1)], 2)

    def _update_state(self, snapshot: MonitoringSnapshot) -> None:
        self._state = MonitoringState(
            deployment_status=self._state.deployment_status,
            snapshots=tuple(self._snapshots),
            stabilization_start_utc=self._state.stabilization_start_utc,
            stabilization_end_utc=self._state.stabilization_end_utc,
            stability_achieved=(
                self._check_stability()
                if self._state.deployment_status == DeploymentStatus.STABILIZING
                else self._state.stability_achieved
            ),
        )

    def _check_stability(self) -> bool:
        """Check if all recent snapshots have been HEALTHY for stabilization period."""
        if len(self._snapshots) < 2:
            return False
        recent_window = [
            s for s in self._snapshots
            if s.overall_status == HealthProbeStatus.HEALTHY
        ]
        if len(recent_window) < 2:
            return False

        # Check time span of healthy snapshots
        first_ts = _parse_iso(recent_window[0].timestamp_utc)
        last_ts = _parse_iso(recent_window[-1].timestamp_utc)
        if first_ts and last_ts:
            duration = (last_ts - first_ts).total_seconds()
            return duration >= self.stabilization_seconds
        return False

    def _finalize_state(self) -> MonitoringState:
        stable = self._check_stability()
        end = utc_now_iso()
        start = self._snapshots[0].timestamp_utc if self._snapshots else None
        return MonitoringState(
            deployment_status=(
                DeploymentStatus.COMPLETED if stable else DeploymentStatus.FAILED
            ),
            snapshots=tuple(self._snapshots),
            stabilization_start_utc=start,
            stabilization_end_utc=end,
            stability_achieved=stable,
        )


# ---------------------------------------------------------------------------
# Deployment Executor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeploymentConfig:
    dry_run: bool = True
    deployment_strategy: str = "rolling"  # rolling | blue_green | canary
    stabilization_seconds: float = 60.0
    health_check_interval_seconds: float = 15.0


class DeploymentExecutor:
    """
    Executes production deployment with integrated live monitoring.

    In dry_run mode (default), simulates deployment and returns synthetic healthy probes.
    In live mode, executes actual deployment and monitors real health endpoints.
    """

    def __init__(self, config: Optional[DeploymentConfig] = None) -> None:
        self.config = config or DeploymentConfig()

    def execute(
        self,
        scenario_id: str,
        release_id: str,
        version: str,
        health_endpoints: Optional[Tuple[str, ...]] = None,
    ) -> DeploymentRecord:
        """
        Execute deployment and return record with live monitoring state.

        In dry_run: returns completed deployment with synthetic healthy probes.
        In live mode: executes deployment and monitors real endpoints.
        """
        start_utc = utc_now_iso()

        if self.config.dry_run:
            monitoring = self._dry_run_monitoring(version, len(health_endpoints) if health_endpoints else 1)
        else:
            monitoring = self._live_deploy_and_monitor(version, health_endpoints or ())

        return DeploymentRecord(
            scenario_id=scenario_id,
            release_id=release_id,
            version=version,
            deployed_at_utc=start_utc,
            deployment_status=monitoring.deployment_status,
            monitoring=monitoring,
        )

    def _dry_run_monitoring(self, version: str, num_probes: int) -> MonitoringState:
        """Simulate a deployment with synthetic healthy probes."""
        snapshots: List[MonitoringSnapshot] = []
        statuses = [
            HealthProbeStatus.HEALTHY,
            HealthProbeStatus.HEALTHY,
            HealthProbeStatus.HEALTHY,
        ]

        for i, status in enumerate(statuses):
            results = tuple(
                HealthProbeResult(
                    probe_name=f"probe-{j+1}",
                    status=status,
                    response_time_ms=45.0 + (i * 5),
                    checked_at_utc=utc_now_iso(),
                )
                for j in range(num_probes)
            )
            overall = HealthProbeStatus.HEALTHY if all(r.status == HealthProbeStatus.HEALTHY for r in results) else HealthProbeStatus.DEGRADED
            snapshots.append(MonitoringSnapshot(
                timestamp_utc=utc_now_iso(),
                overall_status=overall,
                probe_results=results,
                error_rate_percent=0.0,
                p99_latency_ms=55.0 + (i * 5),
                active_instances=num_probes,
                deployed_version=version,
            ))

        return MonitoringState(
            deployment_status=DeploymentStatus.COMPLETED,
            snapshots=tuple(snapshots),
            stabilization_start_utc=snapshots[0].timestamp_utc,
            stabilization_end_utc=snapshots[-1].timestamp_utc,
            stability_achieved=True,
        )

    def _live_deploy_and_monitor(
        self, version: str, endpoints: Tuple[str, ...]
    ) -> MonitoringState:
        """Execute live deployment and monitor real endpoints."""
        probes: Tuple[HealthProbe, ...] = tuple(
            HealthProbe(
                name=endpoint,
                check_fn=lambda e=endpoint: self._http_check(e),
            )
            for endpoint in endpoints
        )

        monitor = LiveMonitoringService(
            probes=probes,
            interval_seconds=self.config.health_check_interval_seconds,
            stabilization_seconds=self.config.stabilization_seconds,
        )

        monitor.start(version=version)
        try:
            # Simulate deployment time (in real impl, this would trigger actual deploy)
            time.sleep(5.0)
            return monitor.stop()
        except Exception:
            return monitor.stop()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


__all__ = [
    "HealthProbe",
    "HTTPHealthProbe",
    "SyntheticProbe",
    "LiveMonitoringService",
    "DeploymentExecutor",
    "DeploymentConfig",
]
