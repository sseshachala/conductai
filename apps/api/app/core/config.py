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
    vercel_webhook_secret: str = ""
    github_webhook_secret: str = ""
    # Railway — used by the Deploy Delegator workflow and Railway integration blocks
    railway_api_token: str = ""
    railway_project_id: str = ""    # Delegator project ID on Railway
    railway_environment_id: str = ""  # Production environment ID (auto-fetched if blank)
    railway_backend_service_id: str = ""   # delegator-backend service ID
    railway_frontend_service_id: str = ""  # delegator-ui service ID

    # CORS — comma-separated allowed origins.
    # Defaults to "*" in development only. Must be explicitly set in production.
    allowed_origins: str = "*"

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
    # env var set per-environment). These platform-level keys are no longer read by the
    # executor. Kept here temporarily so existing .env files don't break on startup.
    # Remove after confirming no workspace relies on the platform fallback.
    modal_token_id: str = ""
    modal_token_secret: str = ""

    # Embeddings — set one provider key to enable the memory block
    openai_api_key: str = ""   # text-embedding-3-small (1536d)
    voyage_api_key: str = ""   # voyage-3-lite (512d) — future

    # Fixture promotion — fallback repo if not derivable from the run's workflow
    github_promotion_repo: str = ""

    # Watchdog — tunable thresholds
    # Slack alerts are per-workspace: token from the workspace's Slack integration,
    # channel from workspace.preferences["watchdog_channel"].
    watchdog_stale_minutes: int = 15
    watchdog_approval_timeout_minutes: int = 120
    watchdog_interval_seconds: int = 60

    # Sentry — leave blank to disable
    sentry_dsn: str = ""
    app_version: str = "1.0.0"

    class Config:
        env_file = ".env"


settings = Settings()

_DEFAULT_ENCRYPTION_KEY = "dev-only-32-byte-key-change-this!"
if settings.environment == "production":
    if settings.encryption_key == _DEFAULT_ENCRYPTION_KEY:
        raise RuntimeError(
            "Default encryption_key detected in production. "
            "Set a strong ENCRYPTION_KEY environment variable before starting."
        )
    if settings.allowed_origins == "*":
        raise RuntimeError(
            "CORS allowed_origins is set to '*' in production. "
            "Set ALLOWED_ORIGINS to a comma-separated list of allowed origins "
            "(e.g. 'https://conductai.ai,https://app.conductai.ai')."
        )
