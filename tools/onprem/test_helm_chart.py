"""Render the customer chart without a cluster, keys, or external services."""
import ast
from pathlib import Path
import subprocess

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / "deploy/helm/conduct"


def render(*overrides, ok=True):
    result = subprocess.run(["helm", "template", "conduct", str(CHART), "--namespace", "conduct",
                             "-f", str(CHART / "customer.example.yaml"), *overrides],
                            capture_output=True, text=True, check=False)
    assert (result.returncode == 0) == ok, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d] if ok else result.stderr


def resource(docs, kind, name):
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == "conduct" + name)


def test_complete_trial_stack():
    docs = render()
    deployments = {d["metadata"]["name"] for d in docs if d["kind"] == "Deployment"}
    assert deployments == {"conduct-" + s for s in ("api", "web", "gateway", "worker", "proxy", "router")}
    assert len([d for d in docs if d["kind"] == "StatefulSet"]) == 2
    assert not any(d["kind"] in ("Secret", "VirtualService", "ClusterPolicy") for d in docs)
    config = resource(docs, "ConfigMap", "")["data"]
    assert config["AUTH_MODE"] == "proxy"
    assert config["API_BASE_URL"] == "https://conduct-api.example.com"
    assert config["CONDUCT_PROXY_URL"] == "https://conduct-gateway.example.com/gateway/v1"


def test_ingress_does_not_bypass_proxy_and_strips_headers():
    docs = render()
    routes = resource(docs, "Ingress", "")["spec"]["rules"]
    assert len(routes) == 3
    assert all(r["http"]["paths"][0]["backend"]["service"]["name"] == "conduct-router" for r in routes)
    caddy = resource(docs, "ConfigMap", "-router")["data"]["Caddyfile"]
    assert caddy.count("header_up -X-Conduct-Proxy-Secret") == 3
    assert "header_up -Authorization" in caddy
    assert "reverse_proxy conduct-proxy:4180" in caddy
    assert "header_up X-Forwarded-Proto https" in caddy


def test_web_gets_only_proxy_secret_not_database_or_provider_keys():
    docs = render()
    container = resource(docs, "Deployment", "-web")["spec"]["template"]["spec"]["containers"][0]
    assert "envFrom" not in container
    refs = [e["valueFrom"]["secretKeyRef"]["key"] for e in container["env"] if "valueFrom" in e]
    assert refs == ["CONSOLE_PROXY_SECRET"]
    proxy = resource(docs, "Deployment", "-proxy")["spec"]["template"]["spec"]["containers"][0]
    assert "--code-challenge-method=S256" in proxy["args"]
    assert "--pass-authorization-header=true" in proxy["args"]


def test_external_data_and_private_registry_and_ca():
    docs = render("--set", "postgres.enabled=false,redis.enabled=false,oidc.caConfigMap=private-ca",
                  "--set", "image.pullSecrets[0].name=registry-auth")
    assert not any(d["kind"] == "StatefulSet" for d in docs)
    for suffix in ("-api", "-gateway", "-worker", "-web", "-proxy", "-router"):
        spec = resource(docs, "Deployment", suffix)["spec"]["template"]["spec"]
        assert spec["imagePullSecrets"] == [{"name": "registry-auth"}]
    api = resource(docs, "Deployment", "-api")["spec"]["template"]["spec"]
    assert any(v.get("configMap", {}).get("name") == "private-ca" for v in api["volumes"])


def test_bootstrap_can_be_disabled_and_is_not_run_by_workers():
    docs = render("--set", "bootstrap.enabled=false")
    for suffix in ("-api", "-gateway", "-worker"):
        init = resource(docs, "Deployment", suffix)["spec"]["template"]["spec"]["initContainers"]
        assert [c["name"] for c in init] == ["migrate"]
    docs = render()
    init = resource(docs, "Deployment", "-api")["spec"]["template"]["spec"]["initContainers"]
    assert [c["name"] for c in init] == ["migrate", "bootstrap"]
    ast.parse(resource(docs, "ConfigMap", "-bootstrap")["data"]["bootstrap.py"])


@pytest.mark.parametrize("setting", ["hosts.api=conduct.example.com", "secrets.existingSecret=",
    "secrets.proxySecret=", "image.api.tag=", "ingress.tlsSecretName=", "oidc.issuer=http://idp.test",
    "bootstrap.workspaceId=invalid", "config.extraEnv.AUTH_MODE=development"])
def test_invalid_settings_fail(setting):
    render("--set", setting, ok=False)


def test_network_policy_keeps_web_private():
    docs = render()
    policy = resource(docs, "NetworkPolicy", "-web")
    peers = policy["spec"]["ingress"][0]["from"]
    assert [p["podSelector"]["matchLabels"]["app.kubernetes.io/component"] for p in peers] == ["proxy"]
