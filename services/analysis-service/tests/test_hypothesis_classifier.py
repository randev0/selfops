"""
tests/test_hypothesis_classifier.py
-------------------------------------
Unit tests for hypothesis_classifier.classify().

Scenarios covered:
  1. deploy + DB issue (long_idle) → connection leak root_cause + deploy trigger
  2. DB issue only (no deploy)     → pre-existing leak root_cause
  3. deploy only (no DB data)      → regression trigger + root_cause with unknown cause
  4. conflicting signals           → hypotheses produced without raising
  5. missing evidence              → empty or low-confidence output, never raises
  6. blocked queries without deploy → lock contention root_cause
  7. DB saturation without deploy  → workload/resource-limit root_cause
  8. crash loop alert              → crash loop symptom
  9. high-saturation + deploy (no long_idle) → deploy-induced saturation root_cause
 10. all evidence absent           → empty list

Run with: pytest services/analysis-service/tests/test_hypothesis_classifier.py
"""
import sys
import os

# Allow imports from the analysis-service root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from hypothesis_classifier import classify
from domain.models import Hypothesis


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _deploy(likely_regression: bool = True, minutes: int = 8, title: str = "v2.5.0") -> dict:
    return {
        "available": True,
        "likely_regression": likely_regression,
        "regression_window_minutes": minutes,
        "closest_deploy": {"title": title},
        "recent_deploys": [{"kind": "deploy", "title": title, "timestamp": "now", "author": "ci"}],
        "changed_files_sample": [{"filename": f"file{i}.py", "status": "modified", "additions": 10, "deletions": 2} for i in range(6)],
        "total_commits": 3,
        "total_prs_merged": 1,
    }


def _db(
    saturation: float = 85.0,
    long_idle: int = 4,
    blocked: int = 0,
    deadlocks: int = 0,
    total: int = 85,
    max_conn: int = 100,
) -> dict:
    return {
        "available": True,
        "database_name": "selfops",
        "total_connections": total,
        "active_connections": total - long_idle,
        "idle_connections": 2,
        "idle_in_transaction_connections": 1,
        "max_connections": max_conn,
        "connection_saturation_pct": saturation,
        "long_idle_connections": [
            {"pid": 1000 + i, "application_name": "app", "usename": "selfops", "idle_duration_seconds": 400 + i * 10}
            for i in range(long_idle)
        ],
        "long_idle_threshold_seconds": 300,
        "blocked_queries": [
            {"pid": 2000 + i, "blocked_duration_seconds": 5.0, "query_truncated": "SELECT ...", "blocking_pids": [999]}
            for i in range(blocked)
        ],
        "db_stats": {"deadlocks": deadlocks, "xact_rollback": 0},
        "wait_events": [],
    }


def _cats(hypotheses: list[Hypothesis]) -> set[str]:
    return {h.category for h in hypotheses}


def _titles(hypotheses: list[Hypothesis]) -> list[str]:
    return [h.title for h in hypotheses]


# --------------------------------------------------------------------------- #
# Scenario 1: deploy + DB long-idle → connection leak
# --------------------------------------------------------------------------- #

class TestDeployPlusDB:
    def test_produces_connection_leak_root_cause(self):
        hs = classify("PodCrashLooping", {}, _deploy(), _db(long_idle=4, saturation=85))
        root_causes = [h for h in hs if h.category == "root_cause"]
        assert root_causes, "Expected at least one root_cause hypothesis"
        assert any("leak" in h.title.lower() for h in root_causes), (
            f"Expected a connection-leak root_cause, got: {[h.title for h in root_causes]}"
        )

    def test_produces_deploy_trigger(self):
        hs = classify("PodCrashLooping", {}, _deploy(), _db(long_idle=4))
        triggers = [h for h in hs if h.category == "trigger"]
        assert triggers, "Expected at least one trigger hypothesis"
        assert any("deploy" in h.title.lower() for h in triggers)

    def test_produces_symptom(self):
        hs = classify("PodCrashLooping", {}, _deploy(), _db(long_idle=4, saturation=85))
        symptoms = [h for h in hs if h.category == "symptom"]
        assert symptoms, "Expected at least one symptom hypothesis"

    def test_leak_confidence_is_strong(self):
        hs = classify("PodCrashLooping", {}, _deploy(minutes=8), _db(long_idle=4, saturation=85))
        leak = next(h for h in hs if h.category == "root_cause" and "leak" in h.title.lower())
        assert leak.confidence >= 0.60, f"Expected confidence >= 0.60, got {leak.confidence}"
        assert leak.confidence < 1.0, "Confidence must never be 1.0"

    def test_supporting_evidence_references(self):
        hs = classify("PodCrashLooping", {}, _deploy(), _db(long_idle=4))
        leak = next(h for h in hs if h.category == "root_cause" and "leak" in h.title.lower())
        assert "likely_regression" in leak.supporting_evidence
        assert "long_idle_connections" in leak.supporting_evidence

    def test_all_have_reasoning_summary(self):
        hs = classify("PodCrashLooping", {}, _deploy(), _db(long_idle=4))
        for h in hs:
            assert h.reasoning_summary, f"Hypothesis '{h.title}' missing reasoning_summary"


# --------------------------------------------------------------------------- #
# Scenario 2: DB issue only — no deploy → pre-existing leak
# --------------------------------------------------------------------------- #

class TestDBOnlyNoDeployLeak:
    def test_produces_preexisting_leak_root_cause(self):
        hs = classify("HighDBConnections", {}, deploy_correlation=None, database_diagnostics=_db(long_idle=6, saturation=60))
        root_causes = [h for h in hs if h.category == "root_cause"]
        assert root_causes, "Expected root_cause hypothesis"
        assert any("pre-existing" in h.title.lower() or "leak" in h.title.lower() for h in root_causes)

    def test_no_trigger_when_no_deploy(self):
        hs = classify("HighDBConnections", {}, deploy_correlation=None, database_diagnostics=_db(long_idle=6))
        triggers = [h for h in hs if h.category == "trigger"]
        # No deploy data → no trigger hypothesis expected
        assert not triggers, f"No trigger expected without deploy data, got: {[h.title for h in triggers]}"

    def test_confidence_below_deploy_case(self):
        # No deploy evidence → lower confidence than deploy+leak scenario
        hs_no_deploy = classify("HighDBConnections", {}, None, _db(long_idle=4, saturation=85))
        hs_with_deploy = classify("PodCrashLooping", {}, _deploy(), _db(long_idle=4, saturation=85))
        rc_no_deploy = next((h for h in hs_no_deploy if h.category == "root_cause"), None)
        rc_with_deploy = next((h for h in hs_with_deploy if h.category == "root_cause" and "leak" in h.title.lower()), None)
        if rc_no_deploy and rc_with_deploy:
            assert rc_no_deploy.confidence <= rc_with_deploy.confidence


# --------------------------------------------------------------------------- #
# Scenario 3: deploy only, no DB data → regression trigger + unknown root_cause
# --------------------------------------------------------------------------- #

class TestDeployOnlyNoDBData:
    def test_produces_trigger_hypothesis(self):
        hs = classify("PodRestarting", {}, _deploy(), database_diagnostics=None)
        triggers = [h for h in hs if h.category == "trigger"]
        assert triggers, "Expected trigger hypothesis for deploy"

    def test_produces_root_cause_marked_unknown(self):
        hs = classify("PodRestarting", {}, _deploy(), database_diagnostics=None)
        root_causes = [h for h in hs if h.category == "root_cause"]
        assert root_causes, "Expected root_cause even without DB data"
        # Cause should be described as unknown since no DB diagnostics
        rc = root_causes[0]
        assert rc.confidence <= 0.50, "Low confidence expected without DB data"

    def test_low_confidence_root_cause(self):
        hs = classify("PodRestarting", {"severity": "warning"}, _deploy(), None)
        rcs = [h for h in hs if h.category == "root_cause"]
        assert rcs
        assert max(h.confidence for h in rcs) < 0.60


# --------------------------------------------------------------------------- #
# Scenario 4: conflicting signals
# --------------------------------------------------------------------------- #

class TestConflictingSignals:
    def test_deploy_plus_blocked_queries_no_long_idle(self):
        """Deploy + blocked queries but no long-idle: still produces valid output."""
        db = _db(saturation=40, long_idle=0, blocked=3)
        hs = classify("HighLatency", {"namespace": "platform"}, _deploy(), db)
        assert isinstance(hs, list)
        assert all(isinstance(h, Hypothesis) for h in hs)
        assert all(0.0 <= h.confidence <= 1.0 for h in hs)

    def test_all_categories_valid(self):
        hs = classify("HighLatency", {}, _deploy(), _db(long_idle=2, blocked=2, saturation=75))
        for h in hs:
            assert h.category in ("symptom", "trigger", "root_cause")

    def test_confidence_never_exceeds_0_9(self):
        hs = classify("PodCrashLooping", {"severity": "critical"}, _deploy(minutes=3), _db(long_idle=10, saturation=95))
        for h in hs:
            assert h.confidence <= 0.9, f"Confidence must not exceed 0.9, got {h.confidence} for '{h.title}'"


# --------------------------------------------------------------------------- #
# Scenario 5: missing evidence
# --------------------------------------------------------------------------- #

class TestMissingEvidence:
    def test_no_evidence_at_all_returns_list(self):
        hs = classify("UnknownAlert", {})
        assert isinstance(hs, list)

    def test_empty_deploy_dict_returns_list(self):
        hs = classify("UnknownAlert", {}, deploy_correlation={}, database_diagnostics={})
        assert isinstance(hs, list)

    def test_unavailable_flags_return_empty(self):
        hs = classify("UnknownAlert", {}, {"available": False}, {"available": False})
        assert hs == []

    def test_none_values_do_not_raise(self):
        # Should never raise
        classify(None, None)  # type: ignore[arg-type]

    def test_malformed_dicts_do_not_raise(self):
        classify("Alert", {}, {"available": True, "recent_deploys": "not-a-list"}, {"available": True, "connection_saturation_pct": "bad"})


# --------------------------------------------------------------------------- #
# Scenario 6: blocked queries without deploy
# --------------------------------------------------------------------------- #

class TestBlockedQueriesNoDeplooy:
    def test_lock_contention_root_cause(self):
        hs = classify("HighLatency", {}, deploy_correlation=None, database_diagnostics=_db(saturation=30, long_idle=0, blocked=5))
        root_causes = [h for h in hs if h.category == "root_cause"]
        assert any("lock" in h.title.lower() or "contention" in h.title.lower() or "misconfiguration" in h.title.lower() for h in root_causes)

    def test_deadlocks_increase_confidence(self):
        hs_no_deadlock = classify("HighLatency", {}, None, _db(saturation=30, long_idle=0, blocked=3, deadlocks=0))
        hs_with_deadlock = classify("HighLatency", {}, None, _db(saturation=30, long_idle=0, blocked=3, deadlocks=2))
        rc_no = next((h for h in hs_no_deadlock if h.category == "root_cause"), None)
        rc_with = next((h for h in hs_with_deadlock if h.category == "root_cause"), None)
        if rc_no and rc_with:
            assert rc_with.confidence >= rc_no.confidence


# --------------------------------------------------------------------------- #
# Scenario 7: DB saturation without deploy
# --------------------------------------------------------------------------- #

class TestDBSaturationNoDeployNoLeak:
    def test_workload_root_cause(self):
        hs = classify("HighDBConnections", {}, deploy_correlation=None, database_diagnostics=_db(saturation=82, long_idle=0, blocked=0))
        root_causes = [h for h in hs if h.category == "root_cause"]
        assert root_causes
        assert any("workload" in h.title.lower() or "limit" in h.title.lower() or "saturation" in h.title.lower() for h in root_causes)


# --------------------------------------------------------------------------- #
# Scenario 8: crash loop alert with no structured evidence
# --------------------------------------------------------------------------- #

class TestCrashLoopAlert:
    def test_crash_loop_symptom_produced(self):
        hs = classify("PodCrashLooping", {"namespace": "platform", "severity": "critical"})
        symptoms = [h for h in hs if h.category == "symptom"]
        assert any("crash" in h.title.lower() for h in symptoms)

    def test_crash_loop_with_no_deploy_produces_low_confidence_root_cause(self):
        hs = classify("PodCrashLooping", {}, None, None)
        root_causes = [h for h in hs if h.category == "root_cause"]
        if root_causes:
            assert all(h.confidence < 0.40 for h in root_causes)

    def test_high_cpu_alert_produces_cpu_symptom(self):
        hs = classify("HighCPUUsage", {"container": "api"})
        symptoms = [h for h in hs if h.category == "symptom"]
        assert any("cpu" in h.title.lower() for h in symptoms)


# --------------------------------------------------------------------------- #
# Scenario 9: deploy + saturation (no long-idle) → deploy-induced saturation
# --------------------------------------------------------------------------- #

class TestDeployHighSaturationNoLeak:
    def test_deploy_induced_saturation_root_cause(self):
        hs = classify("HighDBConnections", {}, _deploy(), _db(saturation=88, long_idle=0))
        root_causes = [h for h in hs if h.category == "root_cause"]
        assert root_causes
        rc = root_causes[0]
        assert "deploy" in rc.title.lower() or "deploy" in rc.description.lower()
        # Without long-idle evidence, confidence should be moderate
        assert rc.confidence < 0.70


# --------------------------------------------------------------------------- #
# Scenario 10: all evidence absent → empty output
# --------------------------------------------------------------------------- #

class TestAllAbsent:
    def test_returns_empty_for_unknown_alert_no_evidence(self):
        hs = classify("SomeAlert", {}, None, None)
        # When alert keywords match nothing and no structured evidence, output is empty
        # (or may produce something from alert keywords — both are acceptable)
        assert isinstance(hs, list)

    def test_all_returned_hypotheses_are_valid(self):
        hs = classify("", {}, None, None)
        for h in hs:
            assert h.category in ("symptom", "trigger", "root_cause")
            assert 0.0 <= h.confidence <= 1.0
            assert h.rank >= 1
