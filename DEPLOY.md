# Deploy Sous to Cloud Run

**All commands below are written for PowerShell** (your shell in VS Code) --
single-line, no `\` continuations. If you use Cloud Shell or Git Bash instead,
see the "bash equivalent" notes on steps 6-7.

## How the deploy works (read this first)

`gcloud run deploy sous --source .` uploads your **local folder** to Cloud
Build, builds the Dockerfile, and runs the image on Cloud Run. **It does not
pull from GitHub.** So you can deploy straight from VS Code -- every file is
there locally, gitignored or not.

Gemini runs on **Vertex AI**, authenticated by the Cloud Run **service account**
-- there is no API key to set or rotate.

Three ignore files, three different jobs:

| File | Controls |
|------|----------|
| `.gitignore` | what goes to your GitHub repo |
| `.gcloudignore` | what gets uploaded to Cloud Build (falls back to `.gitignore` if missing) |
| `.dockerignore` | what the Docker build can see |

---

## Prerequisites

Google Cloud CLI installed (or use Cloud Shell). Sign in:

```powershell
gcloud auth login
```

---

## 1. Create a BILLED project (this is what blocked the API step)

Project IDs are **globally unique** across all of Google Cloud, so a generic id
like `sous-prod` is already taken -- your create fails and you get
"permission denied ... or it may not exist". Pick a unique id (change the suffix).

```powershell
gcloud projects list
```
```powershell
gcloud projects create sous-prod-2026mj --name="Sous"
```
```powershell
gcloud billing accounts list
```
```powershell
gcloud billing projects link sous-prod-2026mj --billing-account=ACCOUNT_ID
```
```powershell
gcloud config set project sous-prod-2026mj
```

`ACCOUNT_ID` is from `billing accounts list` (format `0X0X0X-0X0X0X-0X0X0X`).
If a project you own is already listed with billing on, just
`gcloud config set project <that-id>` and skip to step 2.

---

## 2. Enable the required APIs

`aiplatform.googleapis.com` is Vertex AI -- that is what powers Gemini now.

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com bigquery.googleapis.com storage.googleapis.com secretmanager.googleapis.com
```

If this says permission denied, billing is not linked (redo step 1's
`billing projects link`) or you are on the wrong project
(`gcloud config get-value project`).

---

## 3. What gets uploaded (already set up)

A `.gcloudignore` is included so the deploy uploads only what the app needs --
independent of your hackathon `.gitignore`. Nothing to change.

---

## 4. Deploy

> **PowerShell comma trap:** always wrap the `--set-env-vars` / `--update-env-vars` value in double quotes. Unquoted, PowerShell treats the commas as an array operator and mangles the variables into one. Quotes are harmless in bash too.

```powershell
gcloud run deploy sous --source . --region asia-south1 --allow-unauthenticated --set-env-vars "SOUS_PROJECT_ID=sous-prod-2026mj,GEMINI_MODEL=gemini-3.1-flash-lite,VERTEX_LOCATION=global"
```

- If asked to create an Artifact Registry repo, answer **Y**.
- First deploy takes ~3-5 min (build + push + run).
- At the end it prints a **Service URL** like `https://sous-xxxxx.a.run.app`
  -- your public submission link.
- Cloud Run region (asia-south1) and VERTEX_LOCATION (us-central1) are
  independent -- the app calls Vertex in that region over the API.
- Redeploy after any change by rerunning the same command.

---

## 5. Gemini: no API key needed (Vertex AI)

Nothing to paste. Gemini is called through Vertex AI using the Cloud Run service
account. You only need Vertex enabled (step 2) and the Vertex AI User role
(step 6).

Model / region note: if the app log shows a Vertex `404 model not found`, that
model id is not served in that region. Fix by changing the env vars (us-central1
has the widest Gemini availability):

```powershell
gcloud run services update sous --region asia-south1 --update-env-vars "VERTEX_LOCATION=global,GEMINI_MODEL=gemini-3.1-flash-lite"
```

The app runs fine even if Vertex is unreachable -- it falls back to deterministic
ranking. Vertex only adds the live negotiation narrative.

---

## 6. Grant the service account its roles

Cloud Run runs as a service account that needs BigQuery + Vertex AI permissions.

**PowerShell** -- find the service account, then grant three roles:

```powershell
$SA = gcloud run services describe sous --region asia-south1 --format="value(spec.template.spec.serviceAccountName)"
```
```powershell
if (-not $SA) { $PN = gcloud projects describe sous-prod-2026mj --format="value(projectNumber)"; $SA = "$PN-compute@developer.gserviceaccount.com" }
$SA
```
```powershell
gcloud projects add-iam-policy-binding sous-prod-2026mj --member="serviceAccount:$SA" --role="roles/bigquery.jobUser"
```
```powershell
gcloud projects add-iam-policy-binding sous-prod-2026mj --member="serviceAccount:$SA" --role="roles/bigquery.dataViewer"
```
```powershell
gcloud projects add-iam-policy-binding sous-prod-2026mj --member="serviceAccount:$SA" --role="roles/aiplatform.user"
```

*Bash equivalent (Cloud Shell / Git Bash):* `SA=$(gcloud run services describe sous --region asia-south1 --format="value(spec.template.spec.serviceAccountName)")` then the same three `add-iam-policy-binding` lines using `$SA`.

---

## 7. Migrate the recipes table (once)

Copy the 2.23M-row table from the sandbox into this billed project:

```powershell
bq show --format=prettyjson sous-500915:sous | Select-String location
```
```powershell
bq mk --dataset --location=US sous-prod-2026mj:sous
```
```powershell
bq cp sous-500915:sous.recipes sous-prod-2026mj:sous.recipes
```
```powershell
bq query --use_legacy_sql=false 'SELECT COUNT(*) AS n FROM `sous-prod-2026mj.sous.recipes`'
```

Use the location from the first command in the `bq mk` (e.g. `US`). The verify
query is single-quoted so PowerShell leaves the backticks alone (they are SQL,
not PowerShell escapes).

*Bash equivalent:* replace `| Select-String location` with `| grep -i location`,
and wrap the SQL in double quotes with escaped backticks:
`bq query --use_legacy_sql=false "SELECT COUNT(*) AS n FROM \`sous-prod-2026mj.sous.recipes\`"`

---

## 8. Test

Open the Service URL, edit the walk-in stock, click "Fire today's specials".

- With BigQuery live: needs step 7 (table) and step 6 (roles).
- Live negotiation text: needs Vertex enabled (step 2) + aiplatform.user (step 6).
  Otherwise the app falls back to deterministic ranking -- still works.

For a quick LOCAL run against Vertex (no key), authenticate ADC once:

```powershell
gcloud auth application-default login
```

---

## Troubleshooting

```text
PowerShell error: "Missing expression after unary operator '--'"
  -> you pasted a multi-line command with '\'. Use the single-line versions above.

Permission denied to enable service / "or it may not exist"
  -> project id not owned or not created (unique-id problem) OR billing not linked. Step 1.

The caller does not have permission
  -> your account is not Owner/Editor on the project (IAM).

Vertex "404 model not found" or PERMISSION_DENIED on aiplatform
  -> wrong model/region (change VERTEX_LOCATION / GEMINI_MODEL, step 5), or the
     service account is missing roles/aiplatform.user (step 6), or the Vertex AI
     API is not enabled (step 2).

Build fails at "COPY static/"
  -> deploy from the folder containing static/ (it is present in your Sous folder).

Container failed to start / listen on PORT
  -> Dockerfile already binds Streamlit to $PORT; do not override the CMD.

App loads but BigQuery errors
  -> do steps 6 and 7.

First request after idle is slow
  -> normal Cloud Run cold start; fine for a recorded demo.
```

Repo: https://github.com/MabelHsu/sous-chef
