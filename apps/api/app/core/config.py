from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://marshal:marshal@postgres:5432/marshal"

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://") and "+psycopg2" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    redis_url: str = "redis://redis:6379"
    anthropic_api_key: str = ""
    encryption_key: str = "dev-only-32-byte-key-change-this!"
    debug: bool = True
    # Base URL for callbacks (approval webhooks, etc.)
    api_base_url: str = "http://localhost:8000"
    # Frontend URL — used for trace links in Slack/email notifications
    app_url: str = "https://conductai.ai"
    # Slack signing secret for verifying interactive component payloads
    slack_signing_secret: str = ""
    # Clerk (optional — if unset, all requests use the dev workspace)
    clerk_secret_key: str = ""
    clerk_frontend_api: str = ""  # e.g. "clerk.your-domain.com"
    clerk_audience: str = ""      # set to the expected aud claim to enable audience verification
    # Email — system-level default; can also be added per-workspace in Settings
    resend_api_key: str = ""
    email_from: str = "Conduct AI <notifications@conductai.ai>"
    # Webhook secrets
    clerk_webhook_secret: str = ""   # Clerk signing secret (whsec_…) for user.created events
    vercel_webhook_secret: str = ""
    github_webhook_secret: str = ""
    # CORS — comma-separated allowed origins.
    # Empty string = no CORS (blocks all cross-origin). Must be explicitly set.
    # Example: ALLOWED_ORIGINS=https://conductai.ai,https://app.conductai.ai
    allowed_origins: str = ""

    # Environment — used to gate dev-only defaults (e.g. encryption key check)
    environment: str = "development"

    # Logging
    log_level: str = "INFO"

    # Admin — used to approve waitlisted users via POST /projects/admin/approve
    admin_secret: str = ""

    # CLI / server-to-server API key — bypasses Clerk auth
    cli_api_key: str = ""
    cli_workspace_id: str = ""  # workspace the CLI api key is scoped to

    # Modal sandbox — DEPRECATED: runtime now uses workspace BYO credentials (MODAL_TOKEN_ID
        # Embeddings — set one provider key to enable the memory block
    openai_api_key: str = ""   # text-embedding-3-small (1536d)
    voyage_api_key: str = ""   # voyage-3-lite (512d) — future

    # Pricing registry overrides (optional).
    # MODEL_PRICING_OVERRIDES_JSON format:
    # {
    #   "version": "2026-06-10",
    #   "providers": {
    #     "anthropic": {"claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75}},
    #     "openai": {"gpt-4.1-mini": {"input": 0.4, "output": 1.6}}
    #   }
    # }
    pricing_registry_version: str = "2026-06-04-default"
    pricing_overrides_json: str = ""

    # Fixture promotion — fallback repo if not derivable from the run's workflow
    github_promotion_repo: str = ""

    # Runtime deterministic execution budgets (phase 2 reliability defaults)
    default_max_cost_usd: float = 5.0

    # Watchdog — tunable thresholds
    # Slack alerts are per-workspace: token from the workspace's Slack integration,
    # channel from workspace.preferences["watchdog_channel"].
    watchdog_stale_minutes: int = 15
    watchdog_approval_timeout_minutes: int = 120
    watchdog_interval_seconds: int = 60

    # reCAPTCHA v3 — used to verify anonymous playbook submissions
    recaptcha_secret_key: str = ""
    recaptcha_min_score: float = 0.5

    # Sentry — leave blank to disable
    sentry_dsn: str = ""
    app_version: str = "1.0.0"

    class Config:
        env_file = ".env"


settings = Settings()

_DEFAULT_ENCRYPTION_KEY = "dev-only-32-byte-key-change-this!"
if settings.environment not in ("local", "development") and settings.encryption_key == _DEFAULT_ENCRYPTION_KEY:
    raise RuntimeError(
        "ENCRYPTION_KEY must be set in non-local environments. Refusing to start."
    )
if settings.environment == "production":
    if settings.allowed_origins == "*":
        raise RuntimeError(
            "CORS allowed_origins is set to '*' in production. "
            "Set ALLOWED_ORIGINS to a comma-separated list of allowed origins "
            "(e.g. 'https://conductai.ai,https://app.conductai.ai')."
        )
    import logging as _logging
    _prod_log = _logging.getLogger(__name__)
    if not settings.clerk_frontend_api:
        _prod_log.warning("SECURITY: CLERK_FRONTEND_API not set — JWT issuer not verified")
    if not settings.clerk_audience:
        _prod_log.warning("SECURITY: CLERK_AUDIENCE not set — JWT audience not verified")
