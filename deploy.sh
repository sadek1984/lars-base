#!/bin/bash
set -e

PROJECT="gen-lang-client-0519489172"
REGION="us-central1"

echo "=== Deploying lars-engine (FastAPI) ==="
gcloud builds submit --config cloudbuild.engine.yaml --project "$PROJECT"
gcloud run services update-traffic lars-engine --to-latest --region "$REGION" --project "$PROJECT"

echo "=== Deploying lars-app (Streamlit) ==="
gcloud builds submit --config cloudbuild.app.yaml --project "$PROJECT"
gcloud run services update-traffic lars-app --to-latest --region "$REGION" --project "$PROJECT"

echo "=== Smoke test ==="
ENGINE_URL=$(gcloud run services describe lars-engine --region "$REGION" --project "$PROJECT" --format="value(status.url)")
APP_URL=$(gcloud run services describe lars-app --region "$REGION" --project "$PROJECT" --format="value(status.url)")

echo "Checking lars-engine at $ENGINE_URL ..."
curl -sf "$ENGINE_URL/health" || echo "WARNING: lars-engine health check failed or /health not defined"

echo "Checking lars-app at $APP_URL ..."
curl -sf -o /dev/null "$APP_URL" && echo "lars-app reachable" || echo "WARNING: lars-app not reachable"

echo "=== Done ==="
echo "Engine: $ENGINE_URL"
echo "App:    $APP_URL"
