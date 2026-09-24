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
    conduct_proxy_url: str = "https://gateway.conductai.ai/gateway/v1"

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

    # #2001 — Gateway Profile v2 rollout switch. When true, the resolver
    # reads the immutable ``gateway_profile_bindings`` table by
    # (workspace, environment, model_alias) and pins the revision through
    # every attempt. When false, the legacy resolver walks the mutable
    # ``gateway_profiles.config`` column. Off by default; flipping it on
    # for a workspace requires an admin to publish at least one v2 profile
    # before any v2 routing kicks in, otherwise the resolver returns None
    # and the existing fail-closed path fires — safe by design.
    guard_gateway_profile_v2: bool = False

    # ── PR 3 canary rollout for Gateway Profile v2 ────────────────────
    # Same shape as ``guard_durable_audit_*`` (#1995) — deterministic
    # per-workspace bucketing on top of the global flag so we can ramp
    # traffic without a code deploy. Precedence at read time:
    #   1. Global ``guard_gateway_profile_v2`` off = feature off everywhere.
    #   2. Global on + workspace in allowlist = on regardless of pct.
    #   3. Global on + pct bucket hit = on.
    # Same workspace always lands in the same bucket for a given pct, so
    # a customer's traffic never oscillates between v1 and v2 mid-session.
    guard_gateway_profile_v2_rollout_pct: int = 0
    # Comma-separated workspace UUIDs. Kept as a plain string so env-var
    # parsing stays simple (pydantic-settings list[str] wants JSON on the
    # env side, which is annoying to set in Render). Wins over pct so a
    # workspace can be dark-launched even at pct=0.
    guard_gateway_profile_v2_allowlist: str = ""

    # #2159 — Tools / function calling on /gateway/v1/completions.
    # PR 1 (this) lands the shim wire-in behind this flag; PR 2 adds
    # the response gate + audit fields. Default OFF so today's
    # ``extra="forbid"`` rejection of ``tools`` is preserved in prod
    # until PR 2 is in — accepting ``tools`` without the response gate
    # would let unscanned tool_call arguments flow back to callers.
    # Flip on per-workspace via env var after PR 2 lands.
    guard_gateway_tools_enabled: bool = False

    # #2155 — Streaming + tools with buffered-delta validation. When on,
    # ``stream=true`` combined with ``tools`` is accepted; the streaming
    # response is wrapped so each tool_call's ``arguments`` fragments
    # are buffered across SSE deltas, run through the response-gate
    # validator + redactor once assembled, and emitted only if
    # validation passes. On failure, a synthetic SSE error frame
    # replaces the tool_call — no raw unsafe bytes reach the client.
    # Default OFF so the shim's current 400 rejection stays live in
    # prod until this is verified end-to-end.
    guard_gateway_tools_stream_enabled: bool = False

    # #2170 PR 3 — brain_block sends stream=true through the canonical
    # /completions shim when this is set (uses SSE reassembly on the
    # adapter side to reconstruct tool_calls). Depends on
    # ``guard_gateway_tools_stream_enabled`` being on at the gateway too
    # — the shim rejects stream+tools without it. Default OFF so the
    # non-streaming path stays live until ops flips both flags.
    guard_brain_streaming_enabled: bool = False

    # #2166 — Vision (image_url content parts). When on, the shim
    # accepts multimodal messages with image_url parts (``https://``
    # and ``data:image/*`` URLs only), enforces per-message image
    # count + per-URL size caps, and hands text parts to the existing
    # redaction path. Anthropic-target conversion + per-image token
    # estimation shipped in PR 2 — default now ON. Ops can flip OFF
    # per-env if a workspace hits provider-side vision limits before
    # our own caps do (should be rare — ours are strictly tighter).
    guard_gateway_vision_enabled: bool = True

    # #2209 PR 3 (Flight Recorder cross-links) — canonical base URL for
    # the Flight Recorder UI. When set, AccountingReader includes
    # deep-links on receipts + aggregates so Lens can hyperlink answers
    # ("this attempt cost $X — see the full request trace"). Blank
    # disables link generation; consumers render request_ids as plain
    # text until #2069 publishes its route + subscribes to this contract.
    #
    # Contract (owned by #2209, subscribed by #2069):
    #   {base}/requests/{request_id}
    #   {base}/requests/{request_id}/attempts/{attempt_ordinal}
    # Flight Recorder MUST resolve those to the request / attempt
    # detail pages. No trailing slash on the base.
    flight_recorder_base_url: str = ""

    # #2001 commit 4 — LiteLLM in-process transport switch. When true,
    # v2 profiles whose targets carry transport=litellm_sdk execute
    # through the embedded LiteLLM SDK (anthropic_messages,
    # responses, chat_completions, token_counter). When
    # false, transport=litellm_sdk targets fall through to the
    # legacy RawHTTPTransport passthrough — safe rollback for the flag.
    # Independent from guard_gateway_profile_v2: a workspace can
    # publish a v2 profile before the in-process transport is enabled,
    # and the transport can be enabled globally before any v2 profile
    # exists.
    guard_litellm_in_process: bool = False

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

    # ── Phase 5 canary rollout (#1995) ────────────────────────────────
    # Two knobs on top of guard_use_durable_audit that let us ramp
    # traffic on prod without a code deploy. Deterministic per-workspace
    # bucketing means the SAME workspace always lands in the same slot
    # of a given percentage — no flapping mid-session between the two
    # writer paths.
    #
    # Rollout: allowlist first (internal test WS), then bump pct 0 → 1
    # → 10 → 25 → 50 → 100, watching guard_audit_failed_total between
    # each step. Rollback = drop pct to 0; workspaces fall back to the
    # legacy single-phase writer immediately, no deploy needed.
    guard_durable_audit_rollout_pct: int = 0
    # Comma-separated workspace UUIDs. Kept as a plain string so env-var
    # parsing stays simple (pydantic-settings list[str] wants JSON on the
    # env side, which is annoying to set in Render). Split at read time
    # via ``durable_audit_allowlist_ids`` below.
    guard_durable_audit_allowlist: str = ""



    # Phase 4 of #1959 — reconciler poll interval. Runs every 120s by
    # default (2× the lease), so an orphan surfaces within one interval
    # of its lease expiring. Set to 0 to disable the daemon; useful in
    # local dev or when the trial worker is the only workload.
    guard_durable_audit_reconciler_seconds: int = 120

    # #1996 — Slack alerter for durable-audit failures. Watches the
    # GUARD_AUDIT_FAILED counter and posts to Conduct's internal ops
    # Slack channel when a per-reason delta crosses threshold. Setting
    # seconds = 0 disables the loop.
    guard_durable_audit_alerter_seconds: int = 60
    guard_durable_audit_alerter_cooldown_seconds: int = 900  # 15 min per reason

    # ── Platform-operator Slack (Conduct's own ops channel) ───────────
    # Distinct from any customer workspace's Slack integration. Used by
    # every internal alerter (durable audit, and eventually fail-open +
    # trial-spend once they're migrated off the legacy webhook path).
    # Missing either value = platform alerters run in log-only mode
    # (safe default in staging / local).
    #
    # ``slack_bot_token`` is Conduct's own workspace bot token (xoxb-*)
    # with ``chat:write`` scope. ``conduct_internal_alert_slack_channel``
    # is the channel name (``#prod-alerts``) or id (``C0…``).
    slack_bot_token: str = ""
    conduct_internal_alert_slack_channel: str = ""

    # /metrics scrape token — audit O01. Empty in production means /metrics
    # refuses every caller (fail-closed). Empty in local/development leaves
    # the endpoint open so devs can `curl /metrics` without extra setup.
    # Scrapers pass the value in header `X-Metrics-Token`.
    metrics_token: str = ""

    def durable_audit_allowlist_ids(self) -> frozenset[str]:
        """Split the comma-separated allowlist env into a set of ids."""
        if not self.guard_durable_audit_allowlist:
            return frozenset()
        return frozenset(
            part.strip()
            for part in self.guard_durable_audit_allowlist.split(",")
            if part.strip()
        )

    def gateway_profile_v2_allowlist_ids(self) -> frozenset[str]:
        """Split the comma-separated v2 allowlist env into a set of ids."""
        if not self.guard_gateway_profile_v2_allowlist:
            return frozenset()
        return frozenset(
            part.strip()
            for part in self.guard_gateway_profile_v2_allowlist.split(",")
            if part.strip()
        )

    def gateway_profile_v2_enabled_for(self, workspace_id: str) -> bool:
        """Deterministic per-workspace enable check for Gateway Profile v2.

        Precedence:
        1. Global kill switch — ``guard_gateway_profile_v2=False`` disables
           the whole feature regardless of allowlist / pct.
        2. Allowlist — explicit workspace UUIDs always on. Wins over pct
           so a workspace can be dark-launched even at pct=0.
        3. Percentage bucket — SHA-256 the workspace id and compare its
           first 4 bytes mod 100 to the rollout pct. Same workspace
           always lands in the same bucket for a given pct, so a
           workspace never oscillates between v1 and v2 mid-session;
           only bumps to pct move it across the line.

        Mirrors ``durable_audit_enabled_for`` on purpose — the two
        canaries have the same shape so operators can reason about
        them the same way.
        """
        if not self.guard_gateway_profile_v2:
            return False
        if workspace_id in self.gateway_profile_v2_allowlist_ids():
            return True
        pct = self.guard_gateway_profile_v2_rollout_pct
        if pct <= 0:
            return False
        if pct >= 100:
            return True
        import hashlib
        digest = hashlib.sha256(workspace_id.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % 100
        return bucket < pct

    def durable_audit_enabled_for(self, workspace_id: str) -> bool:
        """Deterministic per-workspace enable check for #1995 canary.

        Precedence:
        1. Global kill switch — ``guard_use_durable_audit=False`` disables
           the whole feature regardless of allowlist / pct.
        2. Allowlist — explicit workspace UUIDs always on. Wins over pct
           so a workspace can be dark-launched even at pct=0.
        3. Percentage bucket — SHA-256 the workspace id and compare its
           first 4 bytes mod 100 to the rollout pct. Same workspace
           always lands in the same bucket for a given pct, so a
           workspace never oscillates between the durable and legacy
           writer mid-session; only bumps to pct move it across the
           line.
        """
        if not self.guard_use_durable_audit:
            return False
        if workspace_id in self.durable_audit_allowlist_ids():
            return True
        pct = self.guard_durable_audit_rollout_pct
        if pct <= 0:
            return False
        if pct >= 100:
            return True
        import hashlib
        digest = hashlib.sha256(workspace_id.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % 100
        return bucket < pct

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
