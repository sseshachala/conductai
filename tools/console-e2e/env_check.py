"""Check on-prem process configuration without printing any environment values.

Run inside each deployment service with --service api, web, or worker.
This is a configuration check, not proof of network connectivity or full parity.
"""
import argparse
import os
from urllib.parse import urlsplit


def inspect(environment, service):
    errors, warnings = [], []
    common = ("DATABASE_URL", "REDIS_URL", "ENCRYPTION_KEY") if service != "web" else ()
    required = {
        "api": ("AUTH_MODE", "CONSOLE_OIDC_ISSUER", "CONSOLE_OIDC_CLIENT_ID", "CONSOLE_OIDC_JWKS_URL",
                "CONSOLE_PROXY_SECRET", "API_BASE_URL", "APP_URL", "CONDUCT_PROXY_URL", "ALLOWED_ORIGINS",
                "CONDUCT_WEB_URL", "CONDUCT_OAUTH_ISSUER"),
        "web": ("AUTH_MODE", "API_URL", "API_BASE_URL", "APP_URL", "CONSOLE_PROXY_SECRET"),
        "worker": ("AUTH_MODE", "API_BASE_URL", "APP_URL", "CONDUCT_PROXY_URL"),
    }[service]
    for name in (*common, *required):
        if not environment.get(name, "").strip():
            errors.append(name + " is required")
    if environment.get("AUTH_MODE") != "proxy":
        errors.append("AUTH_MODE must select proxy for this on-prem profile")
    for name in ("CLERK_SECRET_KEY", "CLERK_FRONTEND_API", "CLERK_WEBHOOK_SECRET", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"):
        if environment.get(name):
            errors.append(name + " must be removed from this proxy deployment")
    for name in ("ENCRYPTION_KEY", "CONSOLE_PROXY_SECRET"):
        if name in (*common, *required) and len(environment.get(name, "").encode()) < 32:
            errors.append(name + " needs at least 32 bytes")
    for name in ("API_BASE_URL", "APP_URL", "CONDUCT_PROXY_URL", "CONDUCT_WEB_URL", "CONDUCT_OAUTH_ISSUER"):
        value = environment.get(name)
        if not value:
            continue
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if host == "conductai.ai" or host.endswith(".conductai.ai"):
            errors.append(name + " still targets Conduct SaaS")
        if not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
            errors.append(name + " is not a valid deployment URL")
        if parsed.scheme != "https":
            warnings.append(name + " is not HTTPS; restrict any internal HTTP hop to a trusted private network")
    if service == "api" and not environment.get("GUARD_TRIAL_ANTHROPIC_KEY", "").strip():
        warnings.append("GUARD_TRIAL_ANTHROPIC_KEY missing: Try Guard demo will require operator setup")
    for name in ("RESEND_API_KEY", "SLACK_BOT_TOKEN", "GITHUB_WEBHOOK_SECRET", "SENTRY_DSN"):
        if environment.get(name):
            warnings.append(name + " enables an external integration; review outbound access for air-gap deployment")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=("api", "web", "worker"), required=True)
    args = parser.parse_args()
    errors, warnings = inspect(os.environ, args.service)
    for message in errors:
        print("FAIL " + message)
    for message in warnings:
        print("WARN " + message)
    print("Configuration preflight only; values suppressed. Connectivity and feature flags need acceptance testing.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
