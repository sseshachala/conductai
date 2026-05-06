from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://marshal:marshal@postgres:5432/marshal"
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
    # Modal sandbox — when set, Brain tools run in isolated containers
    modal_token_id: str = ""
    modal_token_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
