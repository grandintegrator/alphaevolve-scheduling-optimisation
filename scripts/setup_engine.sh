#!/usr/bin/env bash
# One-time provisioning of the AlphaEvolve engine + assistant, per
# https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/get-started
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get project)}"
ENGINE_ID="${ENGINE_ID:-alpha-evolve-experiment-engine}"
ASSISTANT_ID="default_assistant"   # must be exactly this
TOKEN=$(gcloud auth print-access-token)
BASE="https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/collections/default_collection"

auth=(-H "Content-Type: application/json" -H "x-goog-user-project: ${PROJECT_ID}" -H "Authorization: Bearer ${TOKEN}")

echo "== creating engine ${ENGINE_ID} (idempotent) =="
curl -sS -X POST "${BASE}/engines?engineId=${ENGINE_ID}" "${auth[@]}" -d '{
    "display_name": "'"${ENGINE_ID}"'",
    "data_store_ids": [],
    "solution_type": "SOLUTION_TYPE_GENERATIVE_CHAT"
  }'
echo

echo "== waiting for engine to exist =="
for i in $(seq 1 30); do
  if curl -sS -f -X GET "${BASE}/engines/${ENGINE_ID}" "${auth[@]}" -o /dev/null 2>/dev/null; then
    echo "engine ready"; break
  fi
  sleep 10
done

echo "== creating assistant ${ASSISTANT_ID} (idempotent) =="
curl -sS -X POST "${BASE}/engines/${ENGINE_ID}/assistants?assistantId=${ASSISTANT_ID}" "${auth[@]}" -d '{
    "display_name": "'"${ASSISTANT_ID}"'",
    "description": null,
    "generation_config": null,
    "web_grounding_type": "WEB_GROUNDING_TYPE_UNSPECIFIED",
    "enabled_actions": null,
    "customer_policy": null
  }'
echo

echo "== verify =="
curl -sS -X GET "${BASE}/engines/${ENGINE_ID}/assistants/${ASSISTANT_ID}" "${auth[@]}"
echo
echo "done: PROJECT_ID=${PROJECT_ID} ENGINE_ID=${ENGINE_ID}"
