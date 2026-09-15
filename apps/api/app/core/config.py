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
    debug: bool = False
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
    pricing_registry_version: str = "2026-06-26-proxy"
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

    # Guard proxy — public URL of this server's /proxy endpoint
    conduct_proxy_url: str = "https://api.conductai.ai/proxy"

    # reCAPTCHA v3 — used to verify anonymous playbook submissions
    recaptcha_secret_key: str = ""
    recaptcha_min_score: float = 0.5

    # Sentry — leave blank to disable
    sentry_dsn: str = ""
    app_version: str = "1.0.0"

    # Platform operators — Clerk user IDs that can access cross-tenant ops
    # endpoints (e.g. /guard/trial/ops). Comma-separated. Empty = nobody,
    # which is the correct default; grant explicitly to on-call staff only.
    # A tenant admin role must NEVER be enough on its own — see audit S05.
    platform_operator_clerk_ids: str = ""

    # Trusted ingress proxies — comma-separated CIDR list of load balancers
    # whose X-Forwarded-For headers we trust (e.g. "10.0.0.0/8" for Render's
    # internal LB). If unset, X-Forwarded-For is ignored and request.client.host
    # is used. Never trust the *first* XFF value blindly — audit S12.
    trusted_proxy_cidrs: str = ""

    # Hook journal authentication rollout. Deploy API support and the updated
    # CLI first, then set true after clients have upgraded.
    guard_require_hook_auth: bool = False

    # Phase 1 of #1959 — durable inference audit. Off by default; when set
    # true, the accepted-then-finalized writer becomes the canonical write
    # path. Phase 1 lands the writer functions and schema so callers can
    # opt in incrementally; Phase 2 routes _proxy() through them. Keep off
    # in prod until Phase 5's contract-test gate signs off.
    guard_use_durable_audit: bool = False

    # Seconds after which a still-'accepted' guard_audit_events row is
    # considered orphaned by the Phase 4 reconciler. 630s = 10 min upstream
    # request timeout + 30s buffer, so a legitimate long request (deep-
    # research, high-token completion) is never orphaned mid-flight. The
    # streaming path also renews this lease every 30s while chunks flow.
    # Post-P1-review: original 60s default caused premature orphaning of
    # slow legitimate calls; the streaming heartbeat + this larger buffer
    # closes the observed data-loss window.
    guard_durable_audit_lease_seconds: int = 630

    # How often the streaming _wrap in guard/router.py renews an in-flight
    # row's lease. Must be strictly less than the lease so a stream stall
    # gets picked up by the reconciler within one poll interval. Actor-
    # heartbeat pattern (Kubernetes leases, Consul sessions, etcd).
    guard_durable_audit_stream_renew_seconds: int = 30

    # When true, an insert_accepted() failure returns HTTP 503 rather than
    # silently falling back to single-phase record() and forwarding
    # upstream. Contract: 'persist before forwarding'. Set false ONLY in
    # local dev where a broken DB shouldn't block iteration; production
    # must always be fail-closed. Post-P1-review finding 1.
    guard_durable_audit_fail_closed: bool = True

    # Response cache TTL (seconds) for idempotent replay of the same
    # X-Request-Id via the Redis-backed cache. 24h matches typical
    # business retry windows without holding responses indefinitely.
    # Post-P1-review finding 3.
    guard_durable_audit_response_cache_seconds: int = 86400

    # Phase 4 of #1959 — reconciler poll interval. Runs every 120s by
    # default (2× the lease), so an orphan surfaces within one interval
    # of its lease expiring. Set to 0 to disable the daemon; useful in
    # local dev or when the trial worker is the only workload.
    guard_durable_audit_reconciler_seconds: int = 120

    # /metrics scrape token — audit O01. Empty in production means /metrics
    # refuses every caller (fail-closed). Empty in local/development leaves
    # the endpoint open so devs can `curl /metrics` without extra setup.
    # Scrapers pass the value in header `X-Metrics-Token`.
    metrics_token: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"  # tolerate stray legacy env vars so app boots cleanly


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

# 1.2 — Warn on missing JWT verification vars in all non-dev environments
# TODO: change to RuntimeError once CLERK_AUDIENCE + CLERK_FRONTEND_API are set on Render
if settings.environment not in ("local", "development"):
    import logging as _logging
    _env_log = _logging.getLogger(__name__)
    if not settings.clerk_frontend_api:
        _env_log.warning("SECURITY: CLERK_FRONTEND_API not set — JWT issuer not verified")
    if not settings.clerk_audience:
        _env_log.warning("SECURITY: CLERK_AUDIENCE not set — JWT audience not verified")
