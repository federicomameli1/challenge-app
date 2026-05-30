"""Tests for backend/health_bridge.py — K8s item parsing, rollup logic, SSE state."""

import pytest

from backend.health_bridge import (
    AppHealthSnapshot,
    _is_degraded,
    _is_healthy,
    _is_out_of_sync,
    _item_to_snapshot,
    _snapshot_payload,
    _STATE,
    _now_iso,
)


def _snap(**kwargs) -> AppHealthSnapshot:
    defaults = dict(
        app="test-app",
        cluster="in-cluster",
        namespace="default",
        sync_status="Synced",
        health_status="Healthy",
        operation_phase="Succeeded",
        revision="abc123",
        received_at=_now_iso(),
    )
    defaults.update(kwargs)
    return AppHealthSnapshot(**defaults)


# ---------------------------------------------------------------------------
# _item_to_snapshot
# ---------------------------------------------------------------------------

class TestItemToSnapshot:
    def _argocd_item(self, name="verdict", health="Healthy", sync="Synced",
                     cluster="in-cluster", namespace="verdict", revision="abc") -> dict:
        return {
            "metadata": {"name": name},
            "spec": {"destination": {"name": cluster, "namespace": namespace}},
            "status": {
                "health": {"status": health},
                "sync": {"status": sync, "revision": revision},
                "operationState": {"phase": "Succeeded"},
            },
        }

    def test_basic_fields_parsed(self):
        item = self._argocd_item()
        snap = _item_to_snapshot(item)
        assert snap.app == "verdict"
        assert snap.health_status == "Healthy"
        assert snap.sync_status == "Synced"
        assert snap.cluster == "in-cluster"
        assert snap.namespace == "verdict"
        assert snap.revision == "abc"

    def test_missing_status_defaults_to_unknown(self):
        item = {"metadata": {"name": "app"}, "spec": {}, "status": {}}
        snap = _item_to_snapshot(item)
        assert snap.health_status == "Unknown"
        assert snap.sync_status == "Unknown"

    def test_missing_operation_state_empty_string(self):
        item = self._argocd_item()
        item["status"].pop("operationState")
        snap = _item_to_snapshot(item)
        assert snap.operation_phase == ""

    def test_received_at_is_set(self):
        snap = _item_to_snapshot(self._argocd_item())
        assert snap.received_at is not None
        assert "T" in snap.received_at


# ---------------------------------------------------------------------------
# Rollup predicates
# ---------------------------------------------------------------------------

class TestRollupPredicates:
    def test_healthy_and_synced_is_healthy(self):
        snap = _snap(health_status="Healthy", sync_status="Synced")
        assert _is_healthy(snap)
        assert not _is_degraded(snap)
        assert not _is_out_of_sync(snap)

    def test_degraded_health(self):
        snap = _snap(health_status="Degraded", sync_status="Synced")
        assert _is_degraded(snap)
        assert not _is_healthy(snap)

    def test_missing_health_is_degraded(self):
        snap = _snap(health_status="Missing", sync_status="Synced")
        assert _is_degraded(snap)

    def test_out_of_sync_not_degraded(self):
        snap = _snap(health_status="Healthy", sync_status="OutOfSync")
        assert _is_out_of_sync(snap)
        assert not _is_degraded(snap)
        assert not _is_healthy(snap)

    def test_degraded_and_out_of_sync_counts_as_degraded_not_oos(self):
        snap = _snap(health_status="Degraded", sync_status="OutOfSync")
        assert _is_degraded(snap)
        assert not _is_out_of_sync(snap)

    def test_progressing_not_healthy_not_degraded(self):
        snap = _snap(health_status="Progressing", sync_status="Synced")
        assert not _is_healthy(snap)
        assert not _is_degraded(snap)
        assert not _is_out_of_sync(snap)


# ---------------------------------------------------------------------------
# _snapshot_payload (rollup counts)
# ---------------------------------------------------------------------------

class TestSnapshotPayload:
    def setup_method(self):
        _STATE.clear()

    def teardown_method(self):
        _STATE.clear()

    def test_empty_state_zero_counts(self):
        payload = _snapshot_payload()
        assert payload.apps_total == 0
        assert payload.apps_healthy == 0
        assert payload.apps_degraded == 0
        assert payload.apps_out_of_sync == 0

    def test_counts_healthy(self):
        _STATE["a"] = _snap(app="a", health_status="Healthy", sync_status="Synced")
        _STATE["b"] = _snap(app="b", health_status="Healthy", sync_status="Synced")
        payload = _snapshot_payload()
        assert payload.apps_total == 2
        assert payload.apps_healthy == 2

    def test_counts_degraded(self):
        _STATE["a"] = _snap(app="a", health_status="Degraded", sync_status="Synced")
        payload = _snapshot_payload()
        assert payload.apps_degraded == 1
        assert payload.apps_healthy == 0

    def test_counts_out_of_sync(self):
        _STATE["a"] = _snap(app="a", health_status="Healthy", sync_status="OutOfSync")
        payload = _snapshot_payload()
        assert payload.apps_out_of_sync == 1
        assert payload.apps_healthy == 0

    def test_apps_sorted_by_cluster_then_name(self):
        _STATE["b"] = _snap(app="b", cluster="prod")
        _STATE["a"] = _snap(app="a", cluster="prod")
        _STATE["c"] = _snap(app="c", cluster="mgmt")
        payload = _snapshot_payload()
        names = [s.app for s in payload.apps]
        assert names == ["c", "a", "b"]
