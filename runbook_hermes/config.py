from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    # Backend switches
    obs_backend: str = "mock"
    deploy_backend: str = "mock"
    trace_backend: str = "mock"
    store_dir: Path = Path(".runbook_hermes_store")

    # Real observability / deploy adapter configuration
    prometheus_base_url: str = ""
    prometheus_auth_token: str = ""
    prometheus_tenant: str = ""
    prometheus_timeout_seconds: int = 5
    loki_base_url: str = ""
    loki_auth_token: str = ""
    loki_tenant: str = ""
    loki_timeout_seconds: int = 5
    trace_base_url: str = ""
    trace_auth_token: str = ""
    trace_provider_kind: str = "mock"
    trace_timeout_seconds: int = 5
    deploy_api_base_url: str = ""
    deploy_api_token: str = ""
    deploy_timeout_seconds: int = 5
    rollback_backend_kind: str = "mock"
    rollout_app_namespace: str = "default"

    # Generic controlled action executor shells. These are intentionally
    # disabled by default; production adapters must be wired explicitly.
    action_execution_backend: str = "none"  # none|demo_file|custom_http|kubernetes|argocd
    action_execution_api_base_url: str = ""
    action_execution_api_token: str = ""
    action_execution_timeout_seconds: int = 5

    # Local payment demo state. These files are mounted into the demo payment
    # service, so a controlled rollback can change only the demo system.
    demo_deploy_state_file: Path = Path("data/payment_demo/deployments.json")
    demo_version_file: Path = Path("data/payment_demo/runtime/payment-service-version.txt")
    controlled_execution_enabled: bool = False
    recovery_verify_window: str = "2m"
    recovery_error_rate_threshold: float = 0.02

    # Feishu / Lark
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    feishu_callback_base_url: str = ""
    feishu_bot_webhook_url: str = ""
    feishu_bot_secret: str = ""

    # WeCom / 企业微信
    wecom_corp_id: str = ""
    wecom_agent_id: str = ""
    wecom_secret: str = ""
    wecom_token: str = ""
    wecom_encoding_aes_key: str = ""
    wecom_callback_base_url: str = ""

    # Optional cheap model / OpenAI-compatible interface.
    # Hermes itself owns the real provider runtime. These values are kept here
    # so the Runbook API layer can call a lightweight summarizer when needed.
    runbook_model_provider: str = "openai-compatible"
    runbook_model_name: str = "openrouter/auto"
    runbook_model_base_url: str = "https://openrouter.ai/api/v1"
    runbook_model_api_key: str = ""
    runbook_model_temperature: float = 0.0
    runbook_model_enabled: bool = False
    runbook_max_turns: int = 12


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _path_env(name: str, default: str) -> Path:
    return Path(os.getenv(name, default).strip() or default)


def load_settings() -> Settings:
    return Settings(
        obs_backend=os.getenv("OBS_BACKEND", os.getenv("RUNBOOK_OBS_BACKEND", "mock")).strip() or "mock",
        deploy_backend=os.getenv("DEPLOY_BACKEND", os.getenv("RUNBOOK_DEPLOY_BACKEND", "mock")).strip() or "mock",
        trace_backend=os.getenv("TRACE_BACKEND", os.getenv("RUNBOOK_TRACE_BACKEND", "mock")).strip() or "mock",
        store_dir=Path(os.getenv("RUNBOOK_STORE_DIR", ".runbook_hermes_store")),
        prometheus_base_url=os.getenv("PROMETHEUS_BASE_URL", "").rstrip("/"),
        prometheus_auth_token=os.getenv("PROMETHEUS_AUTH_TOKEN", ""),
        prometheus_tenant=os.getenv("PROMETHEUS_TENANT", ""),
        prometheus_timeout_seconds=_int_env("PROMETHEUS_TIMEOUT_SECONDS", 5),
        loki_base_url=os.getenv("LOKI_BASE_URL", "").rstrip("/"),
        loki_auth_token=os.getenv("LOKI_AUTH_TOKEN", ""),
        loki_tenant=os.getenv("LOKI_TENANT", ""),
        loki_timeout_seconds=_int_env("LOKI_TIMEOUT_SECONDS", 5),
        trace_base_url=os.getenv("TRACE_BASE_URL", "").rstrip("/"),
        trace_auth_token=os.getenv("TRACE_AUTH_TOKEN", ""),
        trace_provider_kind=os.getenv("TRACE_PROVIDER_KIND", os.getenv("TRACE_BACKEND", "mock")) or "mock",
        trace_timeout_seconds=_int_env("TRACE_TIMEOUT_SECONDS", 5),
        deploy_api_base_url=os.getenv("DEPLOY_API_BASE_URL", "").rstrip("/"),
        deploy_api_token=os.getenv("DEPLOY_API_TOKEN", ""),
        deploy_timeout_seconds=_int_env("DEPLOY_TIMEOUT_SECONDS", 5),
        rollback_backend_kind=os.getenv("ROLLBACK_BACKEND_KIND", "mock") or "mock",
        rollout_app_namespace=os.getenv("ROLLOUT_APP_NAMESPACE", "default") or "default",
        action_execution_backend=os.getenv("ACTION_EXECUTION_BACKEND", "none") or "none",
        action_execution_api_base_url=os.getenv("ACTION_EXECUTION_API_BASE_URL", "").rstrip("/"),
        action_execution_api_token=os.getenv("ACTION_EXECUTION_API_TOKEN", ""),
        action_execution_timeout_seconds=_int_env("ACTION_EXECUTION_TIMEOUT_SECONDS", 5),
        demo_deploy_state_file=_path_env("DEMO_DEPLOY_STATE_FILE", "data/payment_demo/deployments.json"),
        demo_version_file=_path_env("DEMO_VERSION_FILE", "data/payment_demo/runtime/payment-service-version.txt"),
        controlled_execution_enabled=_bool_env("RUNBOOK_CONTROLLED_EXECUTION_ENABLED", False),
        recovery_verify_window=os.getenv("RUNBOOK_RECOVERY_VERIFY_WINDOW", "2m"),
        recovery_error_rate_threshold=_float_env("RUNBOOK_RECOVERY_ERROR_RATE_THRESHOLD", 0.02),
        feishu_app_id=os.getenv("FEISHU_APP_ID", ""),
        feishu_app_secret=os.getenv("FEISHU_APP_SECRET", ""),
        feishu_verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
        feishu_encrypt_key=os.getenv("FEISHU_ENCRYPT_KEY", ""),
        feishu_callback_base_url=os.getenv("FEISHU_CALLBACK_BASE_URL", ""),
        feishu_bot_webhook_url=os.getenv("FEISHU_BOT_WEBHOOK_URL", ""),
        feishu_bot_secret=os.getenv("FEISHU_BOT_SECRET", ""),
        wecom_corp_id=os.getenv("WECOM_CORP_ID", ""),
        wecom_agent_id=os.getenv("WECOM_AGENT_ID", ""),
        wecom_secret=os.getenv("WECOM_SECRET", ""),
        wecom_token=os.getenv("WECOM_TOKEN", ""),
        wecom_encoding_aes_key=os.getenv("WECOM_ENCODING_AES_KEY", ""),
        wecom_callback_base_url=os.getenv("WECOM_CALLBACK_BASE_URL", ""),
        runbook_model_provider=os.getenv("RUNBOOK_MODEL_PROVIDER", "openai-compatible"),
        runbook_model_name=os.getenv("RUNBOOK_MODEL_NAME", os.getenv("LLM_MODEL", "openrouter/auto")),
        runbook_model_base_url=os.getenv("RUNBOOK_MODEL_BASE_URL", os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")),
        runbook_model_api_key=os.getenv("RUNBOOK_MODEL_API_KEY", os.getenv("LLM_API_KEY", os.getenv("OPENROUTER_API_KEY", os.getenv("OPENAI_API_KEY", "")))),
        runbook_model_temperature=_float_env("RUNBOOK_MODEL_TEMPERATURE", _float_env("LLM_TEMPERATURE", 0.0)),
        runbook_model_enabled=_bool_env("RUNBOOK_MODEL_ENABLED", _bool_env("LLM_ENABLED", False)),
        runbook_max_turns=_int_env("RUNBOOK_MAX_TURNS", 12),
    )
