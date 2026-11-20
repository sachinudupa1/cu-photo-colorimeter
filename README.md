# Cu-Photo-Colorimeter

A chemistry + AI/ML project exploring whether controlled smartphone photographs can estimate copper(II) concentration in an ammoniacal solution. The system combines image processing, blank-referenced camera measurements, calibration modelling, quality checks, and a human-reviewed model-approval workflow.

> **Scientific status:** the files under `results/synthetic/` are generated from simulated data. They demonstrate the software pipeline only; they are not experimental evidence. No claim of real-world camera accuracy, detection limit, quantification limit, or minimum distinguishable difference should be made until real, independently prepared laboratory samples have been measured and compared with the laboratory colorimeter.

## Project sites

The project contains two separate web applications:

- **Training Console** — private laboratory workspace for authorised team members to collect and verify experimental records, train candidate models, review validation results, and approve a model.
- **Presentation Site** — public project explanation and live-prediction interface. Public predictions become available only after the team approves a model.

Both sites are designed as responsive web applications. On supported mobile browsers, the photo input requests the phone's rear camera (`capture="environment"`) and can also allow photo selection from the device. Camera behavior varies by browser and device; real-phone testing is required.

## Architecture

```text
Training Console (Firebase Hosting: lab)
  └─ Firebase Authentication ID token + teamMember custom claim
       └─ FastAPI backend (Render)
            ├─ Firestore REST API
            │    ├─ training_data
            │    └─ testing_data
            └─ Private Supabase Storage bucket: cu-photo-images
                 ├─ training/     experimental photographs
                 ├─ testing/      public-test photographs
                 └─ models/       candidate models, metadata, active pointer

Presentation Site (Firebase Hosting: presentation)
  └─ blank photo(s) + unknown photo(s)
       └─ FastAPI public prediction endpoint (Render)
            ├─ loads only the approved model pointer from Supabase Storage
            ├─ runs image-quality checks and concentration prediction
            └─ saves the prediction record in Firestore testing_data
```

The browser applications do not access Firestore or Supabase Storage directly. They call the FastAPI backend. Private API routes verify the Firebase ID token and require the `teamMember: true` custom claim. The backend uses Google Application Default Credentials (ADC) for Firebase Authentication verification and Firestore REST access. Firestore client rules deny direct browser reads and writes.

Photographs and model artifacts are stored in a **private Supabase Storage** bucket. The Supabase Secret key is used only by the backend and must never be placed in a `VITE_` variable, committed to Git, or shared in screenshots.

### Two primary Firestore collections

1. `training_data` — one document per independently prepared solution. Roles include `blank`, `standard`, `validation`, and `resolution`. Records include concentration/unit when applicable, colorimeter absorbance, session and camera details, verification status, and private Supabase object paths.
2. `testing_data` — one document per public/live test. It records the prediction, interval, warnings, model version, and private image paths. A teammate can later append the true reference concentration/colorimeter reading. Such feedback is not automatically treated as training data.

Model files and the active-model pointer are stored in Supabase Storage under `models/`; a third Firestore collection is not required.

## Scientific and model workflow

- `blank` — reference solution without copper. Collect fresh blank photographs for each session.
- `standard` — known concentration used to fit the calibration model.
- `validation` — known concentration withheld from fitting and used to compare candidate methods/models.
- `resolution` — independently prepared replicates used for the minimum-distinguishable-difference (MDD) analysis.
- `testing_data` — public/live prediction records. Reference values may be added later for audit and possible deliberate promotion into training data.

The calibration workflow evaluates six simple RGB/channel and linearisation choices using validation data. When the validation set has at least three distinct concentrations, it selects the candidate with the lowest validation MAE. Final performance reporting still requires untouched test data. The colorimeter absorbance is retained as a reference measurement; it is not silently substituted for the prepared concentration as the model target.

The resolution analysis compares adjacent tested concentration levels using Welch's t-test with Holm correction at alpha = 0.05. It requires at least three independently prepared solutions at each concentration level. Multiple photographs of one flask are technical replicates, not independent preparations. The reported MDD is an empirical screening result for the tested phone/light/chemistry arrangement, not a universal camera specification.

Candidate models require human review. The approval workflow checks basic calibration conditions and requires at least three distinct labelled validation concentrations for normal approval. A provisional approval path exists for demonstration use, but a provisional model must not be represented as experimentally validated.

## Current implementation status

Implemented and exercised locally:

- React/Vite Training Console and Presentation Site.
- FastAPI backend and Firebase Authentication custom-claim protection for team routes.
- Firestore REST adapter (used instead of the gRPC Firestore client in this environment).
- Supabase Storage adapter for private photographs and model artifacts.
- Synthetic image-processing, calibration, agent, and resolution tests.
- Local end-to-end API checks and live read/write/delete checks against Firestore and Supabase.

Not yet complete:

- Collection of real laboratory photographs and independently prepared standards.
- Training and scientific validation using real samples.
- Public Render deployment and production Firebase Hosting deployment.
- Real-device camera testing on the final hosted URLs.

Do not describe the project as scientifically validated until the real-lab validation work has been completed and documented.

## Technology stack

- **Frontend:** React, Vite, Firebase Web SDK.
- **API:** Python, FastAPI, Uvicorn.
- **Image processing and modelling:** NumPy, pandas, SciPy, scikit-learn, Pillow, Matplotlib.
- **Identity and database:** Firebase Authentication, Cloud Firestore (Firestore REST API).
- **Object storage:** Supabase Storage (private bucket).
- **Planned hosting:** Firebase Hosting for the two static websites; Render Docker web service for the Python API.

## Local development

### Prerequisites

- Python 3.11 or newer (Python 3.13 has been used in local development).
- Node.js and npm.
- Firebase CLI for Hosting deployment.
- Google Cloud CLI for local ADC authentication and Firebase Admin operations.

### 1. Create and activate the Python environment

From the repository root in VS Code PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 2. Configure the backend environment

Copy the template:

```powershell
Copy-Item backend/.env.example backend/.env
```

Set these values in the local `backend/.env` file:

```dotenv
FIREBASE_PROJECT_ID=your-firebase-project-id
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_BUCKET_NAME=cu-photo-images
SUPABASE_SECRET_KEY=your-server-only-supabase-secret-key
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174
REQUIRE_APP_CHECK=false
MAX_UPLOAD_BYTES=3145728
MAX_PHOTOS_PER_SAMPLE=8
MAX_PREDICTIONS_PER_MINUTE_PER_PROCESS=6
MODEL_STORAGE_PREFIX=models
```

Keep `backend/.env` private. Never commit it or copy its secret value into frontend environment variables.

For local Firebase Admin and Firestore REST access, authenticate ADC once:

```powershell
gcloud auth application-default login
```

The currently configured Firebase project must also be accessible to the Google account used for ADC. Do not download a service-account key just for local development when ADC is already working.

### 3. Install and configure the frontend apps

```powershell
Copy-Item apps/training-console/.env.example apps/training-console/.env.local
Copy-Item apps/presentation-site/.env.example apps/presentation-site/.env.local

Push-Location apps/training-console
npm install
Pop-Location

Push-Location apps/presentation-site
npm install
Pop-Location
```

Fill each `.env.local` with the Firebase Web App configuration for that specific app. The two apps use the same Firebase project but have different Web App IDs. For local development, set this in **both** frontend files:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8080/api
```

Firebase Web App configuration is browser configuration, not a service-account credential. Never put the Supabase Secret key or Google service-account JSON into a frontend file or any `VITE_` variable.

### 4. Start the backend and websites

From the repository root, start the backend in one terminal:

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8080
```

Start each website in its own terminal:

```powershell
Set-Location apps/training-console
npm run dev
```

```powershell
Set-Location apps/presentation-site
npm run dev
```

The Vite development URLs are normally `http://localhost:5173` and `http://localhost:5174`. Keep the backend's `ALLOWED_ORIGINS` in sync with the actual browser origins.

### 5. Authorise team members

The Training Console has no public sign-up page. Create team accounts in Firebase Authentication, then grant the `teamMember: true` custom claim using a trusted local administrator session:

```powershell
$env:FIREBASE_PROJECT_ID = "your-firebase-project-id"
.\.venv\Scripts\python.exe scripts/set_team_claims.py teammate1@example.com teammate2@example.com
```

The command requires suitable Firebase Authentication administration permissions. After a claim is granted, the teammate must sign out and sign in again so the refreshed ID token contains the claim. Never share passwords in source control or public chat.

## Tests and builds

Backend tests:

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD"
.\.venv\Scripts\python.exe -m pytest backend\tests -v
```

Core tests (on Windows systems where Application Control blocks the native DLL used by `test_compare_methods.py`, run the remaining suite separately):

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD"
.\.venv\Scripts\python.exe -m pytest -v --ignore=tests/test_compare_methods.py
```

Frontend production builds:

```powershell
Push-Location apps/training-console
npm run build
Pop-Location

Push-Location apps/presentation-site
npm run build
Pop-Location
```

Generate and evaluate synthetic examples:

```powershell
.\.venv\Scripts\python.exe scripts/make_synthetic_data.py --out data/synthetic
.\.venv\Scripts\python.exe scripts/train.py --manifest data/synthetic/manifest.csv --photos data/synthetic/photos
```

Synthetic outputs are software-development fixtures only. Do not mix them with the real experimental dataset or report them as laboratory results.

## Deployment plan

The intended no-billing deployment is:

- **Firebase Hosting (Spark):** hosts the Training Console and Presentation Site as two Hosting sites in one Firebase project, within the applicable no-cost quotas.
- **Render Free Docker Web Service:** hosts the FastAPI backend using the root `Dockerfile`.
- **Supabase Free project:** stores photographs and model artifacts in the private `cu-photo-images` bucket.
- **Firebase Authentication and Firestore:** remain in the existing Firebase project.

This deployment has not yet been completed. Validate the Render service, memory use, API behavior, and real phone uploads before relying on it for a laboratory session.

### Render backend configuration (planned)

Create a Render **Web Service** from this repository and select Docker. Use the root `Dockerfile`. Render provides HTTPS and a `PORT` environment variable; the Dockerfile starts Uvicorn on that port. Configure the following environment variables in the Render dashboard (never in Git):

```text
FIREBASE_PROJECT_ID=your-firebase-project-id
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_BUCKET_NAME=cu-photo-images
SUPABASE_SECRET_KEY=<server-only Supabase Secret key>
GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/firebase-service-account.json
ALLOWED_ORIGINS=https://YOUR_LAB_SITE.web.app,https://YOUR_PRESENTATION_SITE.web.app
REQUIRE_APP_CHECK=false
MAX_UPLOAD_BYTES=3145728
MAX_PHOTOS_PER_SAMPLE=8
MAX_PREDICTIONS_PER_MINUTE_PER_PROCESS=6
MODEL_STORAGE_PREFIX=models
```

Add the Google service-account JSON as a **Render Secret File** named `firebase-service-account.json`; Render exposes secret files under `/etc/secrets/`. The `GOOGLE_APPLICATION_CREDENTIALS` variable points ADC to that file. Create a dedicated least-privilege service account for this backend and grant only the required Firestore data access and Firebase Authentication read access. Keep the JSON key out of the repository and rotate/revoke it if exposed. Service-account keys are sensitive, long-lived credentials; prefer an attached workload identity when the hosting platform supports it.

The Render free service has limited resources, can spin down after inactivity, and has an ephemeral filesystem. The application therefore stores persistent photos and model files in Supabase and records in Firestore, not on the Render local disk. The free service's memory limit can constrain model training; monitor logs and memory during tests. If training exceeds the free instance's resources, train locally or use a suitably sized service rather than assuming the free tier can handle every workload.

After Render creates the service, set the production API base URL in **both** frontend `.env.local` files before building:

```dotenv
VITE_API_BASE_URL=https://YOUR_RENDER_SERVICE.onrender.com/api
```

Add both exact Firebase Hosting origins to Render's `ALLOWED_ORIGINS` value. The API is public for the Presentation Site's prediction endpoint; private team routes continue to require a valid Firebase ID token and the `teamMember` claim.

### Firebase Hosting configuration

The repository's `firebase.json` defines two Hosting targets:

- `lab` → `apps/training-console/dist`
- `presentation` → `apps/presentation-site/dist`

There are intentionally **no Cloud Run rewrites** in `firebase.json`. Each frontend calls the Render API using its production `VITE_API_BASE_URL`.

Install and sign in to Firebase CLI, then configure the local project/site target mapping:

```powershell
npm install -g firebase-tools
firebase login
Copy-Item .firebaserc.example .firebaserc
```

Edit `.firebaserc` with the real Firebase project ID and apply the Hosting site IDs:

```powershell
firebase target:apply hosting lab YOUR_LAB_HOSTING_SITE_ID --project YOUR_FIREBASE_PROJECT_ID
firebase target:apply hosting presentation YOUR_PRESENTATION_HOSTING_SITE_ID --project YOUR_FIREBASE_PROJECT_ID
```

Build both websites with the production Render API URL set in their local environment files, then deploy the rules and Hosting sites:

```powershell
firebase deploy --only firestore:rules --project YOUR_FIREBASE_PROJECT_ID
firebase deploy --only hosting:lab,hosting:presentation --project YOUR_FIREBASE_PROJECT_ID
```

The `storage.rules` file is retained as a legacy reference only; Firebase Storage is not part of the current architecture and is not deployed by this configuration.

### Free-tier limitations

- Firebase Hosting and Firestore have project-level no-cost quotas. Monitor usage in Firebase Console; exceeding Spark quotas can cause service limitations until the next quota period or a plan change.
- Render Free web services sleep after 15 minutes without inbound traffic and typically take about a minute to wake. They have limited memory and an ephemeral filesystem.
- Supabase Free Storage has a finite project storage allowance and per-file/bucket restrictions. The current `cu-photo-images` bucket is private and limited to 3 MB per object; the backend also enforces a 3 MB photo upload limit.

Check the providers' current plan limits before deployment or a public demonstration; free-tier terms and quotas can change.

## Security rules and repository hygiene

- `firestore.rules` denies direct browser/client access. The backend authenticates with Google credentials and accesses Firestore through its REST API.
- `storage.rules` is not used by the current application; photographs and model artifacts use the private Supabase bucket.
- Keep `.env`, `.env.local`, `backend/.env`, service-account JSON files, Supabase Secret keys, raw laboratory photographs, and private experimental records out of Git.
- Firebase Web App configuration is expected to be present in browser builds, but it is not a substitute for server-side authorization.
- Never set the Supabase bucket to public. The backend alone should use the Supabase Secret key.

## License

No license has been added yet. Unless a license is added, the public repository is visible but normal copyright restrictions still apply; public visibility alone does not grant permission to reuse or redistribute the code.
