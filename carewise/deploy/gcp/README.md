# Running CareWise on Google Cloud

The backend runs on **Cloud Run** in Sydney (`australia-southeast1`), with **Cloud SQL** for
Postgres, **Vertex AI** for Gemini and embeddings, **Secret Manager** for secrets, and **Cloud
Scheduler** for reminders. The frontend stays on Vercel.

```
Vercel (frontend) ──► Cloud Run: carewise-api ──► Cloud SQL Postgres   (unix socket, same region)
                           │      ▲            └──► Vertex AI: Gemini + embeddings (no API key)
                           │      └── Cloud Scheduler: /internal/cron/reminders every minute,
                           │                           /hourly, /morning
                           └── secrets from Secret Manager
```

## What changes from Render + Neon

- **No AI API key and no daily cap.** Vertex AI signs in with the Cloud Run service account, and
  is billed per use on your Google Cloud project. The AI Studio free tier's 20 requests a day,
  which kept stopping the live chat, no longer applies.
- **Background jobs are triggered from outside.** Cloud Run stops the app between requests, so
  timers inside it can't be relied on (`SCHEDULER_MODE=external`). Cloud Scheduler calls
  `/internal/cron/<job>` instead, with a secret header. Reminders are checked every minute, which
  is cheap because Cloud SQL is always on anyway. Those calls also keep the service warm, so
  visitors rarely hit a cold start.
- **No sleep, no compute allowance.** Cloud SQL doesn't pause, so the Neon outage can't recur.

## Before you start (once)

1. Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), then sign in:
   ```bash
   gcloud auth login
   ```
2. In the [Cloud console](https://console.cloud.google.com), create a project and **link a
   billing account**. Cloud SQL and Vertex AI need billing.
3. Strongly recommended: **Billing → Budgets & alerts → Create budget** (e.g. US$25 a month), so
   you get an email before costs surprise you.

## Deploy

From the repository root, in Git Bash:

```bash
PROJECT_ID=your-project-id bash carewise/deploy/gcp/setup.sh
```

To keep push notifications and email working, first copy these values from Render into your own
terminal. The script stores them in Secret Manager and never prints them.

```bash
export VAPID_PUBLIC_KEY=... VAPID_PRIVATE_KEY=... VAPID_CLAIM_EMAIL=... RESEND_API_KEY=...
```

Existing push subscriptions only keep working with the **same** VAPID keys. A new `SECRET_KEY` is
generated, so everyone signs in once more after the move.

The script checks that the Gemini model is available on Vertex AI before creating anything costly.
If it isn't, it stops and tells you to set `GEMINI_MODEL`. It's safe to run again, for example to
deploy new code.

## Moving your data from Neon

Do this right after the first deploy, before pointing the frontend at the new backend. It
**replaces** whatever is in Cloud SQL with a copy of Neon, and runs on Google Cloud as a one-off
job, so no database tools are needed on your machine.

1. Store the Neon connection string (direct, without `-pooler`) as a secret. Paste it into your
   own terminal when asked; don't put it in chat or in a file.
   ```bash
   read -rs OLD && printf '%s' "$OLD" | gcloud secrets create carewise-old-database-url --data-file=- && unset OLD
   ```
2. Run the copy with the backend's own image:
   ```bash
   REGION=australia-southeast1
   IMAGE=$(gcloud run services describe carewise-api --region $REGION --format='value(spec.template.spec.containers[0].image)')
   CONNECTION=$(gcloud sql instances describe carewise-db --format='value(connectionName)')
   gcloud run jobs deploy carewise-copy-data --image "$IMAGE" --region $REGION \
     --service-account "carewise-api@$(gcloud config get-value project).iam.gserviceaccount.com" \
     --set-cloudsql-instances "$CONNECTION" --max-retries 0 \
     --set-secrets DATABASE_URL=carewise-database-url:latest,OLD_DATABASE_URL=carewise-old-database-url:latest \
     --command python --args=-m,scripts.copy_database
   gcloud run jobs execute carewise-copy-data --region $REGION --wait
   ```
   Its log lists rows copied per table. It refuses to run if the two databases are on different
   migrations.
3. Clean up:
   ```bash
   gcloud run jobs delete carewise-copy-data --region $REGION --quiet
   gcloud secrets delete carewise-old-database-url --quiet
   ```

## Switch the frontend over

In Vercel, set `VITE_API_BASE` to `https://<your Cloud Run URL>/api` and redeploy. Check
`https://<your Cloud Run URL>/health?db=true`: `"database": "postgres"`, and query times of a few
milliseconds. Once everything works, delete the Render service and the Neon project.

## Costs (rough, Sydney region)

| Service | Expect |
|---|---|
| Cloud SQL, `db-f1-micro` + 10 GB | about US$10–15 a month. This is the main cost; it runs around the clock. |
| Cloud Run | usually within the free tier at this traffic |
| Vertex AI (Gemini, embeddings) | per token: cents for light use. Each message is about 3 calls. |
| Cloud Scheduler | free (3 jobs) |
| Secret Manager, Artifact Registry, Cloud Build | cents, or free-tier |

Prices change, so check the [pricing calculator](https://cloud.google.com/products/calculator)
and keep the budget alert on.

## Where data is processed

Cloud Run and Cloud SQL are in Sydney. Vertex AI uses the `global` endpoint, where the newest
Gemini models are served, so prompts may be processed outside Australia. If that matters, set
`VERTEX_LOCATION=australia-southeast1` and choose a model offered in that region.
