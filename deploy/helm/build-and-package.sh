#!/usr/bin/env bash
# Build the two Conduct images and package the Helm chart for PCAI upload.
#
#   REGISTRY   container registry prefix       (default: ghcr.io/conductai)
#   VERSION    image + chart tag               (default: appVersion from Chart.yaml)
#   PUSH       set to 1 to `docker push`       (default: 0)
#
# Examples:
#   ./deploy/helm/build-and-package.sh
#   REGISTRY=harbor.pcai.local/conduct PUSH=1 ./deploy/helm/build-and-package.sh
#
# Output:
#   <REGISTRY>/conduct-api:<VERSION>
#   <REGISTRY>/conduct-web:<VERSION>
#   deploy/helm/conduct-<VERSION>.tgz
set -euo pipefail

cd "$(dirname "$0")/../.."

REGISTRY="${REGISTRY:-ghcr.io/conductai}"
VERSION="${VERSION:-$(awk '/^appVersion:/ {gsub(/"/, "", $2); print $2}' deploy/helm/conduct/Chart.yaml)}"
PUSH="${PUSH:-0}"

API_IMAGE="${REGISTRY}/conduct-api:${VERSION}"
WEB_IMAGE="${REGISTRY}/conduct-web:${VERSION}"

echo "→ Building ${API_IMAGE}"
docker build -f apps/api/Dockerfile --target prod -t "${API_IMAGE}" apps/api

echo "→ Building ${WEB_IMAGE}"
docker build -f apps/web/Dockerfile --target prod -t "${WEB_IMAGE}" .

if [[ "${PUSH}" == "1" ]]; then
  echo "→ Pushing ${API_IMAGE}"
  docker push "${API_IMAGE}"
  echo "→ Pushing ${WEB_IMAGE}"
  docker push "${WEB_IMAGE}"
fi

echo "→ Packaging chart"
docker run --rm \
  -v "$PWD/deploy/helm/conduct:/chart" \
  -v "$PWD/deploy/helm:/out" \
  alpine/helm:latest package /chart -d /out

echo
echo "✓ Done"
echo "  API image: ${API_IMAGE}"
echo "  Web image: ${WEB_IMAGE}"
echo "  Chart:     deploy/helm/conduct-${VERSION}.tgz"
if [[ "${PUSH}" != "1" ]]; then
  echo
  echo "  (Skipped push; set PUSH=1 to publish images.)"
fi
