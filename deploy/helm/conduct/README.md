# Conduct private-cloud Helm chart

## Status

This chart is a packaging foundation, not a turnkey HPE PCAI or air-gapped
Keycloak installation. It predates the console proxy topology verified in
PR #2304. Do not deploy it unchanged expecting that topology.

Start with the [on-prem deployment and acceptance guide](../../../docs/reference/onprem-deployment.md)
for the working Docker evaluation, identity setup, configuration and acceptance
commands. Hosted Keycloak compatibility does not establish disconnected acceptance.

## Existing components

The templates include API, Gateway, worker and web Deployments, single-replica
PostgreSQL/pgvector and Redis StatefulSets, an Istio VirtualService and an optional
Kyverno label policy. Inspect `values.yaml` and the rendered manifests before use.
Resource defaults are not production sizing recommendations.

## Required packaging work

- Package oauth2-proxy with confidential OIDC, PKCE and secure session cookies.
- Wire API/Gateway proxy authentication and web runtime configuration consistently.
- Mount customer CA bundles and sanitize incoming identity headers.
- Separate browser authentication ingress from machine API/Gateway traffic.
- Support explicitly provisioned initial workspaces and identity mappings.
- Support externally managed PostgreSQL/Redis without deploying unused StatefulSets.
- Run migrations as a controlled deployment step, not racing API replicas.
- Add readiness, disruption, backup/restore and upgrade acceptance for the target environment.
- Pin all images and publish an offline artifact inventory and checksums.
- Validate HPE Import Framework inputs against the customer's PCAI version,
  ingress, storage, registry and secret-management configuration.

Use externally managed secrets through `secrets.existingSecret`; verify its key
contract against the templates. Never put credentials in command-line flags or
committed Helm values. Clerk mode requires its Clerk configuration; proxy mode
requires the separate configuration documented in the deployment guide.

## Packaging checks

These commands validate/package the chart, not the deployed authentication flow:

```sh
helm lint deploy/helm/conduct
helm template conduct deploy/helm/conduct --namespace conduct
helm package deploy/helm/conduct
```

Run console, delegation/revocation and controlled-outage acceptance on the deployed
customer configuration. Disconnected acceptance additionally requires self-hosted
identity, internal model serving, blocked external egress and cold-start evidence.
Preserve PVCs during uninstall or rollback; data deletion is a separate,
explicitly approved operation.
