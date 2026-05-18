from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Sequence

from integrations.observability.deploy_backend import DemoDeployBackend
from integrations.observability.loki_backend import LokiBackend
from integrations.observability.prometheus_backend import PrometheusBackend
from integrations.observability.trace_backend import JaegerTraceBackend, TempoTraceBackend

from .config import Settings, load_settings
from .resources import resource_path
from .service_profiles import first_present, load_service_profile

MOCK_ROOT = resource_path("data", "runbook_mock")


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
        return {"status": "success", "service": service, "query": query, "window": window, "data": self._read("mock_metrics", service), "adapter": "mock"}

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
        return [
            {
                "evidence_id": "ev_deploy_not_configured",
                "source": "deploy",
                "service": service,
                "summary": "Set DEPLOY_BACKEND=demo_file, argocd or kubernetes to enable deploy history.",
                "raw_ref": "deploy://not-configured",
                "confidence": 0.3,
            }
        ]


def _command_result(command: Sequence[str], timeout: int, env: Dict[str, str] | None = None) -> Dict[str, Any]:
    try:
        completed = subprocess.run(list(command), capture_output=True, text=True, timeout=timeout, check=False, env=env)
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "ok": completed.returncode == 0,
        }
    except FileNotFoundError:
        return {"ok": False, "returncode": 127, "stderr": f"command not found: {command[0] if command else ''}", "stdout": ""}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "returncode": 124, "stderr": f"timeout after {timeout}s: {exc}", "stdout": exc.stdout or ""}


class DeployBackend:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.demo = DemoDeployBackend(settings.demo_deploy_state_file, settings.demo_version_file)

    def _profile(self, service: str) -> Dict[str, Any]:
        return load_service_profile(service)

    def _kube_base(self) -> List[str]:
        cmd = [self.settings.kubectl_binary]
        if self.settings.kubernetes_kubeconfig:
            cmd.extend(["--kubeconfig", self.settings.kubernetes_kubeconfig])
        if self.settings.kubernetes_context:
            cmd.extend(["--context", self.settings.kubernetes_context])
        return cmd

    def _kubernetes_command(self, service: str, target_revision: str, profile: Dict[str, Any]) -> List[str]:
        rollback = profile.get("rollback") or {}
        namespace = first_present(rollback.get("kubernetes_namespace"), self.settings.kubernetes_namespace, self.settings.rollout_app_namespace, "default")
        workload_kind = first_present(rollback.get("kubernetes_workload_kind"), self.settings.kubernetes_workload_kind, "deployment").lower()
        workload_name = first_present(self.settings.kubernetes_rollout_name, rollback.get("kubernetes_workload_name"), service)
        mode = first_present(self.settings.kubernetes_rollback_mode, "deployment_image").lower()
        cmd = self._kube_base() + ["-n", namespace]
        if mode == "rollout_undo":
            cmd.extend(["argo", "rollouts", "undo", f"rollout/{workload_name}"])
            if target_revision.isdigit():
                cmd.extend(["--to-revision", target_revision])
            return cmd
        if mode == "deployment_undo":
            cmd.extend(["rollout", "undo", f"{workload_kind}/{workload_name}"])
            if target_revision.isdigit():
                cmd.extend(["--to-revision", target_revision])
            return cmd
        container = first_present(self.settings.kubernetes_container, rollback.get("kubernetes_container"), service)
        image_repo = first_present(self.settings.kubernetes_image_repository, rollback.get("image_repository"))
        if not image_repo:
            # Fall back to a Kubernetes-native undo when an immutable image repo is
            # not configured. Operators can set RUNBOOK_K8S_ROLLBACK_MODE for a
            # stricter strategy.
            return self._kube_base() + ["-n", namespace, "rollout", "undo", f"{workload_kind}/{workload_name}"]
        image = f"{image_repo}:{target_revision}"
        return cmd + ["set", "image", f"{workload_kind}/{workload_name}", f"{container}={image}"]

    def _argocd_command(self, service: str, target_revision: str, profile: Dict[str, Any]) -> List[str]:
        rollback = profile.get("rollback") or {}
        app = first_present(self.settings.argocd_app, rollback.get("argocd_app"), service)
        cmd = [self.settings.argocd_binary]
        if self.settings.argocd_server:
            cmd.extend(["--server", self.settings.argocd_server])
        if self.settings.argocd_auth_token:
            cmd.extend(["--auth-token", self.settings.argocd_auth_token])
        cmd.extend(["app", "rollback", app, target_revision])
        return cmd

    def _execute_adapter_command(self, backend: str, command: List[str], dry_run: bool, service: str, target_revision: str, checkpoint_id: str) -> Dict[str, Any]:
        payload = {
            "status": "dry_run_succeeded" if dry_run else "controlled_execution_succeeded",
            "service": service,
            "target_revision": target_revision,
            "dry_run": dry_run,
            "checkpoint_id": checkpoint_id,
            "backend": backend,
            "command": command,
            "raw_ref": f"rollback://{backend}/{service}/{target_revision}",
        }
        if dry_run:
            payload["message"] = f"{backend} rollback command constructed but not executed."
            return payload
        if not self.settings.controlled_execution_enabled:
            payload["status"] = "controlled_execution_disabled"
            payload["message"] = "Set RUNBOOK_CONTROLLED_EXECUTION_ENABLED=true after approval/checkpoint validation to execute real rollback adapters."
            return payload
        env = os.environ.copy()
        result = _command_result(command, timeout=self.settings.deploy_timeout_seconds, env=env)
        payload["execution_result"] = result
        if not result.get("ok"):
            payload["status"] = "execution_failed"
            payload["message"] = f"{backend} rollback command failed."
        else:
            payload["message"] = f"{backend} rollback command executed successfully."
        return payload

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
        profile = self._profile(service)
        backend = self.settings.rollback_backend_kind.lower().strip()
        if backend in {"kubernetes", "k8s"}:
            command = self._kubernetes_command(service, target_revision, profile)
            return self._execute_adapter_command("kubernetes", command, dry_run, service, target_revision, checkpoint_id)
        if backend in {"argocd", "argo_cd", "argo-cd"}:
            command = self._argocd_command(service, target_revision, profile)
            return self._execute_adapter_command("argocd", command, dry_run, service, target_revision, checkpoint_id)
        if backend != "mock":
            return {
                "status": "not_configured",
                "service": service,
                "target_revision": target_revision,
                "dry_run": dry_run,
                "checkpoint_id": checkpoint_id,
                "raw_ref": f"rollback://{service}/{target_revision}",
                "message": "Set ROLLBACK_BACKEND_KIND=mock,demo_file,kubernetes or argocd.",
            }
        return {
            "status": "dry_run_succeeded" if dry_run else "mock_execution_succeeded",
            "service": service,
            "target_revision": target_revision,
            "dry_run": dry_run,
            "checkpoint_id": checkpoint_id,
            "raw_ref": f"rollback://mock/{service}/{target_revision}",
            "backend": "mock",
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
