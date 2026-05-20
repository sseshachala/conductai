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
    # Slack signing secret for verifying interactive component payloads
    slack_signing_secret: str = ""
    # Clerk (optional — if unset, all requests use the dev workspace)
    clerk_secret_key: str = ""
    clerk_frontend_api: str = ""  # e.g. "clerk.your-domain.com"
    # Email — system-level default; can also be added per-workspace in Settings
    resend_api_key: str = ""
    email_from: str = "Delegator <notifications@delegator.dev>"
    # Webhook secrets
    vercel_webhook_secret: str = ""
    github_webhook_secret: str = ""
    # Railway — used by the Deploy Delegator workflow and Railway integration blocks
    railway_api_token: str = ""
    railway_project_id: str = ""    # Delegator project ID on Railway
    railway_environment_id: str = ""  # Production environment ID (auto-fetched if blank)
    railway_backend_service_id: str = ""   # delegator-backend service ID
    railway_frontend_service_id: str = ""  # delegator-ui service ID

    # Admin — used to approve waitlisted users via POST /projects/admin/approve
    admin_secret: str = ""

    # CLI / server-to-server API key — bypasses Clerk auth
    cli_api_key: str = ""
    cli_workspace_id: str = ""  # workspace the CLI api key is scoped to

    # Modal sandbox — when set, Brain tools run in isolated containers
    modal_token_id: str = ""
    modal_token_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
