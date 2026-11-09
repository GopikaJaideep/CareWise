#!/usr/bin/env bash
# Deploy the CareWise backend to Google Cloud: Cloud Run + Cloud SQL + Vertex AI + Cloud Scheduler.
# Safe to run again: existing resources are kept, and the service is redeployed with the latest code.
#
#   PROJECT_ID=your-project bash carewise/deploy/gcp/setup.sh
#
# Optional, copied from your current host so push notifications and email keep working (export
# them in your own terminal first; this script never prints them):
#   VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIM_EMAIL, RESEND_API_KEY, RESEND_FROM_EMAIL
#
# See carewise/deploy/gcp/README.md for what this creates and what it costs.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project id}"
REGION="${REGION:-australia-southeast1}"
SERVICE="${SERVICE:-carewise-api}"
SQL_INSTANCE="${SQL_INSTANCE:-carewise-db}"
SQL_TIER="${SQL_TIER:-db-f1-micro}"
DB_NAME="${DB_NAME:-carewise}"
DB_USER="${DB_USER:-carewise}"
FRONTEND_URL="${FRONTEND_URL:-https://carewise-aibuddy.vercel.app}"
VERTEX_LOCATION="${VERTEX_LOCATION:-global}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.6-flash}"
MORNING_HOUR_UTC="${MORNING_HOUR_UTC:-8}"
SA_NAME="carewise-api"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BACKEND_DIR="$(cd "$(dirname "$0")/../../backend" && pwd)"

step() { printf '\n==> %s\n' "$*"; }
random() { openssl rand -hex 24; }
secret_exists() { gcloud secrets describe "$1" --project "$PROJECT_ID" >/dev/null 2>&1; }
put_secret() {  # name, value (from stdin, so it never appears in a process list)
  if secret_exists "$1"; then
    gcloud secrets versions add "$1" --project "$PROJECT_ID" --data-file=- >/dev/null
  else
    gcloud secrets create "$1" --project "$PROJECT_ID" --replication-policy=automatic --data-file=- >/dev/null
  fi
}

step "Project ${PROJECT_ID}, region ${REGION}"
gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

step "Turning on the APIs CareWise uses"
gcloud services enable run.googleapis.com sqladmin.googleapis.com aiplatform.googleapis.com \
  cloudscheduler.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com iam.googleapis.com

step "Checking that ${GEMINI_MODEL} is available on Vertex AI (${VERTEX_LOCATION})"
HOST="aiplatform.googleapis.com"; [ "$VERTEX_LOCATION" = global ] || HOST="${VERTEX_LOCATION}-aiplatform.googleapis.com"
STATUS="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" -H 'Content-Type: application/json' \
  "https://${HOST}/v1/projects/${PROJECT_ID}/locations/${VERTEX_LOCATION}/publishers/google/models/${GEMINI_MODEL}:generateContent" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Reply with OK"}]}]}')"
if [ "$STATUS" != 200 ]; then
  echo "Vertex AI answered HTTP ${STATUS} for ${GEMINI_MODEL}. Set GEMINI_MODEL to a model listed in"
  echo "Vertex AI's Model Garden for this project (e.g. GEMINI_MODEL=gemini-3.5-flash) and run again."
  exit 1
fi
echo "OK"

step "Service account ${SA} (Vertex AI, Cloud SQL, secrets)"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name="CareWise API"
for role in roles/aiplatform.user roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${SA}" --role="$role" \
    --condition=None >/dev/null
done
# Source deploys are built by Cloud Build as the default compute service account.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role=roles/run.builder --condition=None >/dev/null

step "Cloud SQL Postgres instance ${SQL_INSTANCE} (${SQL_TIER}); the first time takes 5-10 minutes"
if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  gcloud sql instances create "$SQL_INSTANCE" --database-version=POSTGRES_17 --edition=ENTERPRISE \
    --tier="$SQL_TIER" --region="$REGION" --storage-size=10GB --storage-auto-increase \
    --backup-start-time=16:00
fi
CONNECTION="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')"
gcloud sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" >/dev/null 2>&1 || \
  gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"

step "Secrets (Secret Manager)"
if ! secret_exists carewise-database-url; then
  DB_PASSWORD="$(random)"
  if gcloud sql users list --instance="$SQL_INSTANCE" --format='value(name)' | grep -qx "$DB_USER"; then
    gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD" >/dev/null
  else
    gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD" >/dev/null
  fi
  printf 'postgresql://%s:%s@/%s?host=/cloudsql/%s' "$DB_USER" "$DB_PASSWORD" "$DB_NAME" "$CONNECTION" \
    | put_secret carewise-database-url
  unset DB_PASSWORD
fi
secret_exists carewise-secret-key || random | tr -d '\n' | put_secret carewise-secret-key
secret_exists carewise-cron-secret || random | tr -d '\n' | put_secret carewise-cron-secret
SECRETS="DATABASE_URL=carewise-database-url:latest,SECRET_KEY=carewise-secret-key:latest,CRON_SECRET=carewise-cron-secret:latest"
for var in RESEND_API_KEY VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY; do
  name="carewise-$(echo "$var" | tr '[:upper:]_' '[:lower:]-')"
  if [ -n "${!var:-}" ]; then printf '%s' "${!var}" | put_secret "$name"; fi
  if secret_exists "$name"; then SECRETS="${SECRETS},${var}=${name}:latest"; fi
done

step "Deploying ${SERVICE} to Cloud Run (builds the container; a few minutes)"
ENV="LLM_PROVIDER=vertex@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}@VERTEX_LOCATION=${VERTEX_LOCATION}@GEMINI_MODEL=${GEMINI_MODEL}"
ENV="${ENV}@SCHEDULER_MODE=external@CORS_ORIGINS=${FRONTEND_URL}@FRONTEND_URL=${FRONTEND_URL}"
ENV="${ENV}@MORNING_REMINDER_HOUR_UTC=${MORNING_HOUR_UTC}"
[ -n "${VAPID_CLAIM_EMAIL:-}" ] && ENV="${ENV}@VAPID_CLAIM_EMAIL=${VAPID_CLAIM_EMAIL}"
[ -n "${RESEND_FROM_EMAIL:-}" ] && ENV="${ENV}@RESEND_FROM_EMAIL=${RESEND_FROM_EMAIL}"
gcloud run deploy "$SERVICE" --source "$BACKEND_DIR" --region "$REGION" \
  --service-account "$SA" --add-cloudsql-instances "$CONNECTION" --allow-unauthenticated \
  --min-instances 0 --max-instances 3 --cpu 1 --memory 512Mi --cpu-boost --timeout 300 \
  --set-env-vars "^@^${ENV}" --set-secrets "$SECRETS"
URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

step "Cloud Scheduler jobs (reminders every minute, hourly clean-up, morning message)"
CRON_SECRET="$(gcloud secrets versions access latest --secret=carewise-cron-secret)"
schedule() {  # name, cron, job
  local verb=create
  gcloud scheduler jobs describe "$1" --location "$REGION" >/dev/null 2>&1 && verb=update
  gcloud scheduler jobs "$verb" http "$1" --location "$REGION" --schedule "$2" --time-zone=UTC \
    --uri "${URL}/internal/cron/$3" --http-method POST \
    "--$( [ "$verb" = create ] && echo headers || echo update-headers )=X-Cron-Secret=${CRON_SECRET}" \
    --attempt-deadline=120s >/dev/null
}
schedule carewise-reminders "* * * * *" reminders
schedule carewise-hourly "0 * * * *" hourly
schedule carewise-morning "0 ${MORNING_HOUR_UTC} * * *" morning

step "Embedding the knowledge base with Vertex AI"
curl -s -o /dev/null -w 'warm-up: HTTP %{http_code}\n' -X POST -H "X-Cron-Secret: ${CRON_SECRET}" "${URL}/internal/cron/warm"
unset CRON_SECRET

step "Done"
curl -s "${URL}/health?db=true"; echo
cat <<EOF

Backend: ${URL}
Next:
  1. Copy your existing data across (see carewise/deploy/gcp/README.md, "Moving your data").
  2. In Vercel, set VITE_API_BASE=${URL}/api and redeploy the frontend.
EOF
