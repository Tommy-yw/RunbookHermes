from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from integrations.observability.deploy_backend import DemoDeployBackend
from integrations.observability.loki_backend import LokiBackend
from integrations.observability.prometheus_backend import PrometheusBackend
from integrations.observability.trace_backend import JaegerTraceBackend, TempoTraceBackend

from .config import Settings, load_settings

ROOT = Path(__file__).resolve().parent.parent
MOCK_ROOT = ROOT / "data" / "runbook_mock"


class BackendNotConfigured(RuntimeError):
    pass


class MockObservabilityBackend:
    def __init__(self, root: Path = MOCK_ROOT):
        self.root = root

    def _read(self, folder: str, service: str) -> List[Dict[str, Any]]:
        path = self.root / folder / f"{service}.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("items", [])
        return data

    def prom_query(self, service: str, query: str = "", window: str = "15m") -> Dict[str, Any]:
        return {"status": "success", "service": service, "query": query, "window": window, "data": self._read("mock_metrics", service)}

    def prom_top_anomalies(self, service: str, window: str = "15m") -> List[Dict[str, Any]]:
        return self._read("mock_metrics", service)

    def loki_query(self, service: str, query: str = "", start: str = "", end: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        return self._read("mock_logs", service)[:limit]

    def trace_search(self, service: str, start: str = "", end: str = "", error_only: bool = True) -> List[Dict[str, Any]]:
        items = self._read("mock_traces", service)
        if error_only:
            return [i for i in items if i.get("error_rate", 0) > 0 or i.get("error_count", 0) > 0]
        return items

    def recent_deploys(self, service: str, since: str = "2h") -> List[Dict[str, Any]]:
        return self._read("mock_deploys", service)


class RealObservabilityBackend:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.prom = PrometheusBackend(settings.prometheus_base_url, settings.prometheus_auth_token, settings.prometheus_tenant, settings.prometheus_timeout_seconds)
        self.loki = LokiBackend(settings.loki_base_url, settings.loki_auth_token, settings.loki_tenant, settings.loki_timeout_seconds)
        if settings.trace_provider_kind.lower() == "tempo":
            self.trace = TempoTraceBackend(settings.trace_base_url, settings.trace_auth_token, settings.trace_timeout_seconds)
        else:
            self.trace = JaegerTraceBackend(settings.trace_base_url, settings.trace_auth_token, settings.trace_timeout_seconds)
        self.demo_deploy = DemoDeployBackend(settings.demo_deploy_state_file, settings.demo_version_file)

    def prom_query(self, service: str, query: str = "", window: str = "15m") -> Dict[str, Any]:
        return self.prom.prom_query(service, query=query, window=window)

    def prom_top_anomalies(self, service: str, window: str = "15m") -> List[Dict[str, Any]]:
        return self.prom.prom_top_anomalies(service, window=window)

    def loki_query(self, service: str, query: str = "", start: str = "", end: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        return self.loki.loki_query(service, query=query, start=start, end=end, limit=limit)

    def trace_search(self, service: str, start: str = "", end: str = "", error_only: bool = True) -> List[Dict[str, Any]]:
        return self.trace.trace_search(service, start=start, end=end, error_only=error_only)

    def recent_deploys(self, service: str, since: str = "2h") -> List[Dict[str, Any]]:
        if self.settings.deploy_backend in {"demo_file", "payment_demo"}:
            return self.demo_deploy.recent_deploys(service, since=since)
        return [{
            "evidence_id": "ev_deploy_not_configured",
            "source": "deploy",
            "service": service,
            "summary": "Set DEPLOY_BACKEND=demo_file, argocd or custom to enable deploy history.",
            "raw_ref": "deploy://not-configured",
            "confidence": 0.3,
        }]


class DeployBackend:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.demo = DemoDeployBackend(settings.demo_deploy_state_file, settings.demo_version_file)

    def rollback_canary(self, service: str, target_revision: str, dry_run: bool = True, checkpoint_id: str = "") -> Dict[str, Any]:
        if self.settings.rollback_backend_kind in {"demo_file", "payment_demo"}:
            if not dry_run and not self.settings.controlled_execution_enabled:
                return {
                    "status": "controlled_execution_disabled",
                    "service": service,
                    "target_revision": target_revision,
                    "dry_run": dry_run,
                    "checkpoint_id": checkpoint_id,
                    "raw_ref": f"rollback://payment-demo/{service}/{target_revision}",
                    "message": "Set RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true to allow demo-system rollback execution.",
                }
            return self.demo.rollback_canary(service, target_revision, dry_run=dry_run, checkpoint_id=checkpoint_id)
        if self.settings.rollback_backend_kind != "mock":
            return {
                "status": "not_configured",
                "service": service,
                "target_revision": target_revision,
                "dry_run": dry_run,
                "checkpoint_id": checkpoint_id,
                "raw_ref": f"rollback://{service}/{target_revision}",
                "message": "Real rollback adapter shell is present. Implement Argo CD, Argo Rollouts or custom backend here.",
            }
        return {
            "status": "dry_run_succeeded" if dry_run else "mock_execution_succeeded",
            "service": service,
            "target_revision": target_revision,
            "dry_run": dry_run,
            "checkpoint_id": checkpoint_id,
            "raw_ref": f"rollback://mock/{service}/{target_revision}",
        }

    def verify_recovery(self, service: str, window: str = "2m") -> Dict[str, Any]:
        settings = self.settings
        if settings.obs_backend == "real":
            prom = PrometheusBackend(settings.prometheus_base_url, settings.prometheus_auth_token, settings.prometheus_tenant, settings.prometheus_timeout_seconds)
            result = prom.prom_query(service, f'sum(rate(http_requests_total{{service="{service}",status="503"}}[1m]))', window=window)
            return {"status": "verification_query_sent", "service": service, "window": window, "prometheus": result}
        current = ""
        if settings.demo_version_file.exists():
            current = settings.demo_version_file.read_text(encoding="utf-8").strip()
        recovered = current and current != "v2.3.1"
        return {"status": "recovered" if recovered else "still_at_risk", "service": service, "current_revision": current, "window": window}


def get_observability_backend(settings: Settings | None = None):
    settings = settings or load_settings()
    if settings.obs_backend == "mock":
        return MockObservabilityBackend()
    return RealObservabilityBackend(settings)


def get_deploy_backend(settings: Settings | None = None):
    return DeployBackend(settings or load_settings())
