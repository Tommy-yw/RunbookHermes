from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .resources import resource_path


@dataclass(frozen=True)
class Settings:
    # Backend switches
    obs_backend: str = "mock"
    deploy_backend: str = "mock"
    trace_backend: str = "mock"
    store_dir: Path = Path(".runbook_hermes_store")
    store_backend: str = "json"  # json|sqlite|postgres
    store_sqlite_path: Path = Path(".runbook_hermes_store/runbook_store.sqlite3")
    store_postgres_dsn: str = ""

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
    kubernetes_namespace: str = "default"
    kubernetes_context: str = ""
    kubernetes_kubeconfig: str = ""
    kubectl_binary: str = "kubectl"
    kubernetes_rollout_name: str = ""
    kubernetes_workload_kind: str = "deployment"
    kubernetes_container: str = ""
    kubernetes_image_repository: str = ""
    kubernetes_rollback_mode: str = "deployment_image"  # deployment_image|deployment_undo|rollout_undo
    argocd_binary: str = "argocd"
    argocd_server: str = ""
    argocd_auth_token: str = ""
    argocd_app: str = ""
    argocd_project: str = ""

    # Generic controlled action executor shells. These are intentionally
    # disabled by default; production adapters must be wired explicitly.
    action_execution_backend: str = "none"  # none|demo_file|custom_http|kubernetes|argocd
    action_execution_api_base_url: str = ""
    action_execution_api_token: str = ""
    action_execution_timeout_seconds: int = 5
    # Production mutation gates. Keep the old ACTION_EXECUTION_ALLOWED_ACTIONS
    # env var as a compatibility alias, but expose the clearer operations name.
    action_execution_allowed_operations: tuple[str, ...] = ()
    action_execution_confirmation_token: str = "CONFIRM_EXECUTE"
    action_execution_require_second_confirmation: bool = True
    action_execution_audit_log_file: Path = Path(".runbook_hermes_store/audit/actions.jsonl")

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
    runbook_gateway_strict_security: bool = True
    runbook_gateway_allow_unsigned_callbacks: bool = False
    runbook_gateway_replay_window_seconds: int = 600

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

    # RunbookHermes self-evolving memory. Enabled by default and fully local:
    # markdown notebooks + SQLite FTS5 + deterministic HRR vectors. External
    # providers are opt-in and always wrapped by context fencing.
    runbook_memory_enabled: bool = True
    runbook_memory_dir: Path = Path(".runbook_hermes_store/memory")
    runbook_memory_context_limit: int = 6
    runbook_memory_hrr_dim: int = 1024
    runbook_memory_external_provider: str = "none"  # none|honcho|mem0|holographic|retaindb
    runbook_memory_external_mode: str = "tools"  # context|tools|hybrid
    runbook_memory_context_cadence: int = 1
    runbook_memory_injection_frequency: str = "first-turn"

    # Hermes official memory/skill integration. The RunbookHermes domain store
    # remains physically isolated, but is exposed through Hermes MemoryProvider
    # and official Skills discovery.
    runbook_memory_bridge_enabled: bool = True
    runbook_memory_bridge_provider_name: str = "runbook_hermes"
    runbook_memory_router_enabled: bool = True
    runbook_feishu_memory_router_enabled: bool = True
    runbook_skill_publish_enabled: bool = True
    runbook_skill_publish_category: str = "runbooks/runbookhermes"

    # API authentication. Enabled by default for production safety. Set
    # RUNBOOK_API_AUTH_ENABLED=false only for isolated local demos.
    runbook_api_auth_enabled: bool = True
    runbook_api_token: str = ""
    runbook_api_read_only_token: str = ""
    runbook_api_auth_header: str = "x-runbook-token"

    # Lightweight citation RAG. This is intentionally local/offline by default:
    # text/markdown/json documents are chunked into SQLite FTS5 with source
    # citations. External vector stores can be layered later without changing API.
    runbook_rag_enabled: bool = True
    runbook_rag_dir: Path = Path(".runbook_hermes_store/rag")
    runbook_rag_chunk_chars: int = 1200
    runbook_rag_chunk_overlap: int = 160
    runbook_rag_context_limit: int = 5
    runbook_rag_allowed_roots: str = "docs,skills/runbooks,profiles/runbook-hermes,data/runbook_samples,data/runbook_mock,data/runbook_benchmark"
    runbook_rag_embedding_model: str = "local-hash-embedding-v1"
    runbook_rag_embedding_dim: int = 256
    runbook_rag_freshness_half_life_days: int = 180
    runbook_rag_default_permission_scope: str = "public"
    runbook_rag_rerank_enabled: bool = True
    runbook_service_profiles_path: Path = Path("data/runbook_profiles/services.json")

    # Multimodal evidence. Deterministic local parsing is always available;
    # Hermes vision_analyze delegation is opt-in so CI/local demos remain offline.
    runbook_multimodal_enabled: bool = True
    runbook_multimodal_collect_dashboards: bool = True
    runbook_multimodal_use_hermes_vision: bool = False

    # Benchmark/eval isolation. By default eval runs use a temporary store so
    # demos and production incident stores are not polluted.
    runbook_eval_persist_default: bool = False
    runbook_eval_model_assist_enabled: bool = False
    # Optional blend weight for LLM-assisted judge output. Kept at 0 by default
    # so deterministic eval remains the quality gate unless explicitly changed.
    runbook_eval_model_assist_weight: float = 0.0

    # Training / RL / AutoPipeline. This layer exports RunbookAIOps incidents
    # into Hermes-compatible trajectories, SFT records, preference pairs and
    # reward JSONL, then emits dry-run handoff templates for Hermes RL and
    # Alibaba Cloud PAI/DashScope. External training is never launched unless
    # explicitly enabled.
    runbook_training_enabled: bool = True
    runbook_training_dir: Path = Path(".runbook_hermes_store/training")
    runbook_training_max_incidents: int = 100
    runbook_training_min_reward: float = 0.65
    runbook_training_compress_max_chars: int = 6000
    runbook_training_base_model: str = "Qwen/Qwen3-8B"
    runbook_training_external_launch_enabled: bool = False
    runbook_training_external_launch_token: str = ""
    runbook_alicloud_autopipeline_enabled: bool = False
    runbook_alicloud_autopipeline_execute: bool = False


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
    raw = os.getenv(name, "").strip()
    if raw:
        return Path(raw)
    parts = Path(default).parts
    if parts and parts[0] in {"data", "docs", "skills", "profiles", "plugins", "web"}:
        return resource_path(default)
    return Path(default)


def load_settings() -> Settings:
    return Settings(
        obs_backend=os.getenv("OBS_BACKEND", os.getenv("RUNBOOK_OBS_BACKEND", "mock")).strip() or "mock",
        deploy_backend=os.getenv("DEPLOY_BACKEND", os.getenv("RUNBOOK_DEPLOY_BACKEND", "mock")).strip() or "mock",
        trace_backend=os.getenv("TRACE_BACKEND", os.getenv("RUNBOOK_TRACE_BACKEND", "mock")).strip() or "mock",
        store_dir=Path(os.getenv("RUNBOOK_STORE_DIR", ".runbook_hermes_store")),
        store_backend=os.getenv("RUNBOOK_STORE_BACKEND", "json").strip().lower() or "json",
        store_sqlite_path=Path(os.getenv("RUNBOOK_STORE_SQLITE_PATH", os.getenv("RUNBOOK_SQLITE_PATH", os.getenv("RUNBOOK_STORE_DIR", ".runbook_hermes_store") + "/runbook_store.sqlite3"))),
        store_postgres_dsn=os.getenv("RUNBOOK_STORE_POSTGRES_DSN", os.getenv("DATABASE_URL", "")),
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
        kubernetes_namespace=os.getenv("RUNBOOK_K8S_NAMESPACE", os.getenv("KUBERNETES_NAMESPACE", os.getenv("ROLLOUT_APP_NAMESPACE", "default"))) or "default",
        kubernetes_context=os.getenv("RUNBOOK_K8S_CONTEXT", os.getenv("KUBERNETES_CONTEXT", "")),
        kubernetes_kubeconfig=os.getenv("RUNBOOK_KUBECONFIG", os.getenv("KUBECONFIG", "")),
        kubectl_binary=os.getenv("RUNBOOK_KUBECTL_BINARY", os.getenv("KUBECTL_BINARY", "kubectl")) or "kubectl",
        kubernetes_rollout_name=os.getenv("RUNBOOK_K8S_ROLLOUT_NAME", os.getenv("RUNBOOK_K8S_WORKLOAD_NAME", "")),
        kubernetes_workload_kind=os.getenv("RUNBOOK_K8S_WORKLOAD_KIND", "deployment").strip().lower() or "deployment",
        kubernetes_container=os.getenv("RUNBOOK_K8S_CONTAINER", ""),
        kubernetes_image_repository=os.getenv("RUNBOOK_K8S_IMAGE_REPOSITORY", ""),
        kubernetes_rollback_mode=os.getenv("RUNBOOK_K8S_ROLLBACK_MODE", "deployment_image").strip().lower() or "deployment_image",
        argocd_binary=os.getenv("RUNBOOK_ARGOCD_BINARY", os.getenv("ARGOCD_BINARY", "argocd")) or "argocd",
        argocd_server=os.getenv("RUNBOOK_ARGOCD_SERVER", os.getenv("ARGOCD_SERVER", "")),
        argocd_auth_token=os.getenv("RUNBOOK_ARGOCD_AUTH_TOKEN", os.getenv("ARGOCD_AUTH_TOKEN", "")),
        argocd_app=os.getenv("RUNBOOK_ARGOCD_APP", os.getenv("ARGOCD_APP", "")),
        argocd_project=os.getenv("RUNBOOK_ARGOCD_PROJECT", os.getenv("ARGOCD_PROJECT", "")),
        action_execution_backend=os.getenv("ACTION_EXECUTION_BACKEND", "none") or "none",
        action_execution_api_base_url=os.getenv("ACTION_EXECUTION_API_BASE_URL", "").rstrip("/"),
        action_execution_api_token=os.getenv("ACTION_EXECUTION_API_TOKEN", ""),
        action_execution_timeout_seconds=_int_env("ACTION_EXECUTION_TIMEOUT_SECONDS", 5),
        action_execution_allowed_operations=tuple(
            item.strip().lower()
            for item in os.getenv("ACTION_EXECUTION_ALLOWED_TYPES", os.getenv("ACTION_EXECUTION_ALLOWED_OPERATIONS", os.getenv("ACTION_EXECUTION_ALLOWED_ACTIONS", ""))).split(",")
            if item.strip()
        ),
        action_execution_confirmation_token=(os.getenv("ACTION_EXECUTION_CONFIRMATION_TOKEN", os.getenv("ACTION_EXECUTION_SECOND_CONFIRMATION_TOKEN", "CONFIRM_EXECUTE")).strip() or "CONFIRM_EXECUTE"),
        action_execution_require_second_confirmation=_bool_env(
            "ACTION_EXECUTION_REQUIRE_SECOND_CONFIRMATION",
            _bool_env("ACTION_EXECUTION_REQUIRE_SECONDARY_CONFIRMATION", _bool_env("ACTION_EXECUTION_SECOND_CONFIRMATION_REQUIRED", True)),
        ),
        action_execution_audit_log_file=Path(os.getenv("ACTION_EXECUTION_AUDIT_LOG_FILE", ".runbook_hermes_store/audit/actions.jsonl")),
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
        runbook_gateway_strict_security=_bool_env("RUNBOOK_GATEWAY_STRICT_SECURITY", True),
        runbook_gateway_allow_unsigned_callbacks=_bool_env("RUNBOOK_GATEWAY_ALLOW_UNSIGNED_CALLBACKS", False),
        runbook_gateway_replay_window_seconds=_int_env("RUNBOOK_GATEWAY_REPLAY_WINDOW_SECONDS", 600),
        runbook_model_provider=os.getenv("RUNBOOK_MODEL_PROVIDER", "openai-compatible"),
        runbook_model_name=os.getenv("RUNBOOK_MODEL_NAME", os.getenv("LLM_MODEL", "openrouter/auto")),
        runbook_model_base_url=os.getenv("RUNBOOK_MODEL_BASE_URL", os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")),
        runbook_model_api_key=os.getenv("RUNBOOK_MODEL_API_KEY", os.getenv("LLM_API_KEY", os.getenv("OPENROUTER_API_KEY", os.getenv("OPENAI_API_KEY", "")))),
        runbook_model_temperature=_float_env("RUNBOOK_MODEL_TEMPERATURE", _float_env("LLM_TEMPERATURE", 0.0)),
        runbook_model_enabled=_bool_env("RUNBOOK_MODEL_ENABLED", _bool_env("LLM_ENABLED", False)),
        runbook_max_turns=_int_env("RUNBOOK_MAX_TURNS", 12),
        runbook_memory_enabled=_bool_env("RUNBOOK_MEMORY_ENABLED", True),
        runbook_memory_dir=_path_env("RUNBOOK_MEMORY_DIR", os.getenv("RUNBOOK_STORE_DIR", ".runbook_hermes_store") + "/memory"),
        runbook_memory_context_limit=_int_env("RUNBOOK_MEMORY_CONTEXT_LIMIT", 6),
        runbook_memory_hrr_dim=_int_env("RUNBOOK_MEMORY_HRR_DIM", 1024),
        runbook_memory_external_provider=os.getenv("RUNBOOK_MEMORY_EXTERNAL_PROVIDER", "none").strip().lower() or "none",
        runbook_memory_external_mode=os.getenv("RUNBOOK_MEMORY_EXTERNAL_MODE", "tools").strip().lower() or "tools",
        runbook_memory_context_cadence=_int_env("RUNBOOK_MEMORY_CONTEXT_CADENCE", 1),
        runbook_memory_injection_frequency=os.getenv("RUNBOOK_MEMORY_INJECTION_FREQUENCY", "first-turn").strip().lower() or "first-turn",
        runbook_memory_bridge_enabled=_bool_env("RUNBOOK_MEMORY_BRIDGE_ENABLED", True),
        runbook_memory_bridge_provider_name=os.getenv("RUNBOOK_MEMORY_BRIDGE_PROVIDER_NAME", "runbook_hermes").strip() or "runbook_hermes",
        runbook_memory_router_enabled=_bool_env("RUNBOOK_MEMORY_ROUTER_ENABLED", True),
        runbook_feishu_memory_router_enabled=_bool_env("RUNBOOK_FEISHU_MEMORY_ROUTER_ENABLED", True),
        runbook_skill_publish_enabled=_bool_env("RUNBOOK_SKILL_PUBLISH_ENABLED", True),
        runbook_skill_publish_category=os.getenv("RUNBOOK_SKILL_PUBLISH_CATEGORY", "runbooks/runbookhermes").strip().strip("/") or "runbooks/runbookhermes",
        runbook_api_auth_enabled=_bool_env("RUNBOOK_API_AUTH_ENABLED", not _bool_env("RUNBOOK_API_DEMO_INSECURE", False)),
        runbook_api_token=os.getenv("RUNBOOK_API_TOKEN", ""),
        runbook_api_read_only_token=os.getenv("RUNBOOK_API_READ_ONLY_TOKEN", ""),
        runbook_api_auth_header=os.getenv("RUNBOOK_API_AUTH_HEADER", "x-runbook-token").strip() or "x-runbook-token",
        runbook_rag_enabled=_bool_env("RUNBOOK_RAG_ENABLED", True),
        runbook_rag_dir=_path_env("RUNBOOK_RAG_DIR", os.getenv("RUNBOOK_STORE_DIR", ".runbook_hermes_store") + "/rag"),
        runbook_rag_chunk_chars=_int_env("RUNBOOK_RAG_CHUNK_CHARS", 1200),
        runbook_rag_chunk_overlap=_int_env("RUNBOOK_RAG_CHUNK_OVERLAP", 160),
        runbook_rag_context_limit=_int_env("RUNBOOK_RAG_CONTEXT_LIMIT", 5),
        runbook_rag_allowed_roots=os.getenv(
            "RUNBOOK_RAG_INGEST_ROOTS",
            os.getenv("RUNBOOK_RAG_ALLOWED_ROOTS", "docs,skills/runbooks,profiles/runbook-hermes,data/runbook_samples,data/runbook_mock,data/runbook_benchmark"),
        ).strip(),
        runbook_rag_embedding_model=os.getenv("RUNBOOK_RAG_EMBEDDING_MODEL", "local-hash-embedding-v1").strip() or "local-hash-embedding-v1",
        runbook_rag_embedding_dim=_int_env("RUNBOOK_RAG_EMBEDDING_DIM", 256),
        runbook_rag_freshness_half_life_days=_int_env("RUNBOOK_RAG_FRESHNESS_HALF_LIFE_DAYS", 180),
        runbook_rag_default_permission_scope=os.getenv("RUNBOOK_RAG_DEFAULT_PERMISSION_SCOPE", "public").strip() or "public",
        runbook_rag_rerank_enabled=_bool_env("RUNBOOK_RAG_RERANK_ENABLED", True),
        runbook_service_profiles_path=_path_env("RUNBOOK_SERVICE_PROFILES_PATH", "data/runbook_profiles/services.json"),
        runbook_multimodal_enabled=_bool_env("RUNBOOK_MULTIMODAL_ENABLED", True),
        runbook_multimodal_collect_dashboards=_bool_env("RUNBOOK_MULTIMODAL_COLLECT_DASHBOARDS", True),
        runbook_multimodal_use_hermes_vision=_bool_env("RUNBOOK_MULTIMODAL_USE_HERMES_VISION", False),
        runbook_eval_persist_default=_bool_env("RUNBOOK_EVAL_PERSIST_DEFAULT", False),
        runbook_eval_model_assist_enabled=_bool_env("RUNBOOK_EVAL_MODEL_ASSIST_ENABLED", False),
        runbook_eval_model_assist_weight=_float_env("RUNBOOK_EVAL_MODEL_ASSIST_WEIGHT", 0.0),
        runbook_training_enabled=_bool_env("RUNBOOK_TRAINING_ENABLED", True),
        runbook_training_dir=_path_env("RUNBOOK_TRAINING_DIR", os.getenv("RUNBOOK_STORE_DIR", ".runbook_hermes_store") + "/training"),
        runbook_training_max_incidents=_int_env("RUNBOOK_TRAINING_MAX_INCIDENTS", 100),
        runbook_training_min_reward=_float_env("RUNBOOK_TRAINING_MIN_REWARD", 0.65),
        runbook_training_compress_max_chars=_int_env("RUNBOOK_TRAINING_COMPRESS_MAX_CHARS", 6000),
        runbook_training_base_model=os.getenv("RUNBOOK_TRAINING_BASE_MODEL", "Qwen/Qwen3-8B").strip() or "Qwen/Qwen3-8B",
        runbook_training_external_launch_enabled=_bool_env("RUNBOOK_TRAINING_EXTERNAL_LAUNCH_ENABLED", False),
        runbook_training_external_launch_token=os.getenv("RUNBOOK_TRAINING_EXTERNAL_LAUNCH_TOKEN", ""),
        runbook_alicloud_autopipeline_enabled=_bool_env("RUNBOOK_ALICLOUD_AUTOPIPELINE_ENABLED", _bool_env("RUNBOOK_ALICLOUD_AUTOPILINE_ENABLED", False)),
        runbook_alicloud_autopipeline_execute=_bool_env("RUNBOOK_ALICLOUD_AUTOPIPELINE_EXECUTE", _bool_env("RUNBOOK_ALICLOUD_AUTOPILINE_EXECUTE", False)),
    )
