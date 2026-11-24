# Deploying to Google Cloud Run

Everything below runs in the browser. Google Cloud Shell already has `gcloud`, `git` and Docker, so nothing needs to be installed locally.

## 1. Create the Google Cloud project (about 10 minutes)

1. Go to https://console.cloud.google.com and sign in.
2. Create a project: project picker (top left) > **New project**. Name it `battery-dispatch-api`. Note the **Project ID** shown under the name (it may have a number suffix).
3. Link billing: **Billing** > link a billing account. A card is required, but this service stays within the Cloud Run free tier (2 million requests per month) and new accounts receive free credit.
4. Set a budget alert so there are no surprises: **Billing > Budgets & alerts > Create budget**, amount **$5**, alerts at 50%, 90% and 100%.

## 2. First deployment from Cloud Shell (about 10 minutes)

Open Cloud Shell with the `>_` icon at the top right of the console, then run (replace the project ID):

```bash
PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID

# Turn on the services Cloud Run deployments use
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# Allow the default build account to build images from source
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role=roles/run.builder --condition=None

# Get the code and deploy it
git clone https://github.com/ekahorsu/battery-dispatch-api.git
cd battery-dispatch-api
gcloud run deploy battery-dispatch-api --source . --region us-west1 \
  --allow-unauthenticated --max-instances 2 --memory 512Mi
```

If asked to create an Artifact Registry repository, answer **Y**. The build takes about 3 to 5 minutes. At the end, gcloud prints the **Service URL**. Open `<Service URL>/docs` to use the API in the browser, and try it:

```bash
URL=$(gcloud run services describe battery-dispatch-api --region us-west1 --format 'value(status.url)')
curl $URL/health
curl -X POST $URL/dispatch/compare -H "Content-Type: application/json" -d @examples/sample_request.json
```

## 3. Automatic deployment from GitHub (about 10 minutes)

GitHub Actions signs in to Google Cloud with **Workload Identity Federation**: GitHub issues a short-lived OIDC token for each run, and Google exchanges it for temporary credentials. No service account key is created or stored, and only this repository is trusted.

In Cloud Shell:

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
REPO=ekahorsu/battery-dispatch-api

# Service account that deploys, with only the permissions a source deployment needs
gcloud iam service-accounts create github-deployer --display-name "GitHub Actions deployer"
SA=github-deployer@$PROJECT_ID.iam.gserviceaccount.com
for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/cloudbuild.builds.editor \
            roles/artifactregistry.writer roles/storage.admin roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=$ROLE --condition=None --quiet > /dev/null
done

# Trust GitHub's identity tokens, limited to this repository
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global --workload-identity-pool=github --display-name="GitHub provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$REPO'"

# Let workflows from this repository act as the deployer service account
gcloud iam service-accounts add-iam-policy-binding $SA --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"

echo "WIF_PROVIDER: projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-provider"
echo "DEPLOY_SA:    $SA"
```

Put the two printed values and your project ID in the `env` section at the top of `.github/workflows/ci-cd.yml`. They are identifiers, not secrets, so no GitHub secrets are needed.

Now every push to `main` runs the tests, builds and smoke-tests the container, and deploys the new version to Cloud Run. Check progress in the repository's **Actions** tab.

## Costs and clean-up

- `--max-instances 2` caps scaling, and Cloud Run scales to zero when idle, so an unused service costs nothing.
- The budget alert from step 1 emails you long before any meaningful charge.
- To remove the service: `gcloud run services delete battery-dispatch-api --region us-west1`

## Troubleshooting

- **Build fails with a permission error:** rerun the `roles/run.builder` command in step 2 and wait a minute for the permission to apply.
- **Deploy job fails at "auth" with a permission or audience error:** check that the repository name in the provider condition and in the `workloadIdentityUser` binding exactly matches `owner/repository`, and that the workflow has `id-token: write` permission.
- **Deploy job fails with "Permission denied" during the build:** wait a few minutes after granting roles, then re-run the job from the Actions tab.
