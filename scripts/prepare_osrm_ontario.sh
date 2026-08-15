#!/usr/bin/env bash
set -euo pipefail

# Local-only helper. This is not CI/CD and does not deploy anything.
# It prepares an Ontario OSRM MLD road graph from the current Geofabrik OSM
# extract and starts a local routing service on port 5000.

OSRM_DIR="${OSRM_DIR:-data/cache/osrm-ontario}"
PBF_URL="${PBF_URL:-https://download.geofabrik.de/north-america/canada/ontario-latest.osm.pbf}"
IMAGE="${OSRM_IMAGE:-osrm/osrm-backend:latest}"
PORT="${OSRM_PORT:-5000}"
PBF_NAME="ontario-latest.osm.pbf"
BASE_NAME="ontario-latest"

mkdir -p "${OSRM_DIR}"

if [[ ! -f "${OSRM_DIR}/${PBF_NAME}" ]]; then
  echo "Downloading Ontario OpenStreetMap extract from Geofabrik..."
  curl -L --fail --retry 4 --retry-delay 3 \
    "${PBF_URL}" \
    -o "${OSRM_DIR}/${PBF_NAME}"
fi

ABS_DIR="$(cd "${OSRM_DIR}" && pwd)"

echo "Extracting OSRM road graph..."
docker run --rm -t -v "${ABS_DIR}:/data" "${IMAGE}" \
  osrm-extract -p /opt/car.lua "/data/${PBF_NAME}"

echo "Partitioning OSRM graph..."
docker run --rm -t -v "${ABS_DIR}:/data" "${IMAGE}" \
  osrm-partition "/data/${BASE_NAME}.osrm"

echo "Customizing OSRM graph..."
docker run --rm -t -v "${ABS_DIR}:/data" "${IMAGE}" \
  osrm-customize "/data/${BASE_NAME}.osrm"

if docker ps -a --format '{{.Names}}' | grep -qx 'ontario-healthcare-osrm'; then
  docker rm -f ontario-healthcare-osrm >/dev/null
fi

echo "Starting local OSRM Table/Route service on port ${PORT}..."
docker run -d --name ontario-healthcare-osrm \
  -p "${PORT}:5000" \
  -v "${ABS_DIR}:/data" \
  "${IMAGE}" \
  osrm-routed --algorithm mld "/data/${BASE_NAME}.osrm"

echo "OSRM is starting at http://127.0.0.1:${PORT}"
echo "Next: python scripts/build_osrm_matrix.py --base-url http://127.0.0.1:${PORT} --resume"
