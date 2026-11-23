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

Create a service account that GitHub Actions uses to deploy, with only the permissions a source deployment needs:

```bash
gcloud iam service-accounts create github-deployer --display-name "GitHub Actions deployer"
SA=github-deployer@$PROJECT_ID.iam.gserviceaccount.com
for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/cloudbuild.builds.editor \
            roles/artifactregistry.writer roles/storage.admin roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=$ROLE --condition=None --quiet > /dev/null
done
gcloud iam service-accounts keys create key.json --iam-account=$SA
cat key.json
```

Then, in the GitHub repository: **Settings > Secrets and variables > Actions > New repository secret**:

- `GCP_SA_KEY`: paste the full contents of `key.json`
- `GCP_PROJECT_ID`: your project ID

Delete the key file from Cloud Shell afterwards: `rm key.json`. The key is a password; never commit it to the repository.

Now every push to `main` runs the tests, builds and smoke-tests the container, and deploys the new version to Cloud Run. Check progress in the repository's **Actions** tab.

## Costs and clean-up

- `--max-instances 2` caps scaling, and Cloud Run scales to zero when idle, so an unused service costs nothing.
- The budget alert from step 1 emails you long before any meaningful charge.
- To remove the service: `gcloud run services delete battery-dispatch-api --region us-west1`

## Troubleshooting

- **Build fails with a permission error:** rerun the `roles/run.builder` command in step 2 and wait a minute for the permission to apply.
- **`keys create` is blocked by an organization policy:** this applies to work or school Google accounts. Use a personal Google account for the project, or set up Workload Identity Federation instead of a key.
- **GitHub deploy job skipped:** the two secrets are missing or misnamed; the test job still runs.
