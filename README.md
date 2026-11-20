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

**Initial production deployment: live.** The following hosted components are available:

| Component | URL | Current verification |
|---|---|---|
| Training Console | https://cu-photo-lab.web.app | Sign-in and dashboard load on desktop and phone; dashboard currently shows zero records because no laboratory dataset has been collected. |
| Presentation Site | https://cu-photo-colorimeter.web.app | Page sections, navigation, images, and mobile layout checked. The live demo correctly reports that no model has been approved. |
| FastAPI backend | https://cu-photo-api.onrender.com | Render deployment is live; `/health` returns the service health response. |

Implemented and exercised:
- React/Vite Training Console and Presentation Site, deployed to Firebase Hosting.
- FastAPI backend deployed as a Docker web service on Render.
- Firebase Authentication and `teamMember: true` custom-claim protection for private team routes.
- Firestore REST adapter and live Firestore read/write/delete checks.
- Supabase Storage adapter, private bucket configuration, and live upload/download/delete checks.
- Backend automated tests: 19/19 passed after the Firestore REST and Supabase missing-object fixes.
- Broader available test suite: 45/45 passed with `tests/test_compare_methods.py` excluded because Windows Application Control blocked its native dependency during this run.
- Both frontend production builds passed.
- On a phone, the Training Console opens the rear-camera capture interface; the Presentation Site's mobile layout was also checked.

Still pending:
- A real photograph uploaded through the hosted Training Console and verified end-to-end in Supabase Storage and Firestore.
- Collection of real laboratory photographs and independently prepared copper standards.
- Training and scientific validation using real samples, including independent validation and blind-test data.
- Approval of a scientifically validated model for public predictions.

The phone camera interface opening does not by itself verify photo upload or scientific measurement accuracy. Synthetic outputs under `results/synthetic/` demonstrate software workflow only; they are not experimental evidence. Do not claim real-world accuracy, LOD, LOQ, or MDD until the required laboratory validation has been completed and documented.

## Technology stack

- **Frontend:** React, Vite, Firebase Web SDK.
- **API:** Python, FastAPI, Uvicorn.
- **Image processing and modelling:** NumPy, pandas, SciPy, scikit-learn, Pillow, Matplotlib.
- **Identity and database:** Firebase Authentication, Cloud Firestore (Firestore REST API).
- **Object storage:** Supabase Storage (private bucket).
- **Hosting:** Firebase Hosting for the two static websites; Render Docker web service for the Python API.

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

## Live deployment

The initial production deployment is live. The project uses Firebase Spark for the two static websites and Firestore, Render for the Python API, and a private Supabase Storage bucket for photographs and model artifacts.

| Component | Provider | Production URL |
|---|---|---|
| Training Console (`lab`) | Firebase Hosting | https://cu-photo-lab.web.app |
| Presentation Site (`presentation`) | Firebase Hosting | https://cu-photo-colorimeter.web.app |
| FastAPI backend | Render | https://cu-photo-api.onrender.com |
| Backend health check | Render | https://cu-photo-api.onrender.com/health |

### Render backend

The deployed Render Web Service is named `cu-photo-api`, uses the repository-root `Dockerfile`, and is configured in the Singapore region on the Free instance type. The backend listens on Render's `PORT` environment variable.

The Render environment contains the Firebase project ID, Supabase URL/bucket/Secret key, allowed browser origins, upload and prediction limits, model-storage prefix, and these settings:

```text
FIREBASE_PROJECT_ID=cu-photo-colorimeter
SUPABASE_BUCKET_NAME=cu-photo-images
GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/cu-photo-render-runtime.json
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174,https://cu-photo-lab.web.app,https://cu-photo-colorimeter.web.app
REQUIRE_APP_CHECK=false
MAX_UPLOAD_BYTES=3145728
MAX_PHOTOS_PER_SAMPLE=8
MAX_PREDICTIONS_PER_MINUTE_PER_PROCESS=6
MODEL_STORAGE_PREFIX=models
```

`SUPABASE_URL` and `SUPABASE_SECRET_KEY` are also required. The Secret key must remain only in Render's private environment configuration and local `backend/.env`; never commit or expose it in a frontend `VITE_` variable.

The Google service-account JSON is stored in Render as a Secret File named `cu-photo-render-runtime.json`, mounted at `/etc/secrets/cu-photo-render-runtime.json`. `GOOGLE_APPLICATION_CREDENTIALS` points to that mounted file. Never commit the JSON file. The Render service uses a dedicated service account with the required Firestore and Firebase Authentication permissions.

The Render Free instance has limited CPU/memory and may spin down after inactivity. Its local filesystem is ephemeral, so persistent photographs and model artifacts belong in Supabase Storage and structured records belong in Firestore. Test real upload and model-training workloads before relying on the Free instance for a laboratory session; larger training jobs may need to run locally or on a larger compute service.

App Check enforcement is currently disabled (`REQUIRE_APP_CHECK=false`). The public prediction endpoint is intentionally accessible without team login; private team endpoints still require a valid Firebase ID token and the `teamMember` claim. The current per-process prediction limit is a basic safeguard, not global abuse protection. Review App Check and stronger rate limiting before wider public use.

### Firebase Hosting websites

The two Firebase Hosting targets are:

- `lab` â†’ site ID `cu-photo-lab` â†’ `apps/training-console/dist`
- `presentation` â†’ site ID `cu-photo-colorimeter` â†’ `apps/presentation-site/dist`

There are no Cloud Run rewrites. Each frontend calls the Render API directly using `VITE_API_BASE_URL=https://cu-photo-api.onrender.com/api`, configured in its local, Git-ignored `.env.production.local` file. The Render `ALLOWED_ORIGINS` value must include both exact Hosting origins.

The real Firebase project/site mapping is stored in the ignored local `.firebaserc` file. Do not commit `.firebaserc`; `.firebaserc.example` is the safe public template.

To rebuild and redeploy the two websites after frontend changes, run these commands from the repository root after ensuring each app's `.env.production.local` contains the production API URL:

```powershell
Push-Location apps/training-console
npm ci
npm run build
Pop-Location

Push-Location apps/presentation-site
npm ci
npm run build
Pop-Location

firebase deploy --only hosting:lab,hosting:presentation --project cu-photo-colorimeter
```

The Render service is connected to the GitHub repository's `main` branch. Deploy backend changes from the updated commit using Render's deploy controls (or its configured auto-deploy behavior). The Firebase Hosting sites are deployed with the Firebase CLI command above.

### Current operational limitations

- No real laboratory dataset has been collected yet, and no scientifically validated model has been approved. The public demo therefore does not provide live concentration predictions yet.
- The Training Console's rear-camera interface has been opened successfully on a phone, but an actual laboratory photo upload through the hosted UI and its end-to-end persistence have not yet been verified.
- Firebase Spark, Render Free, and Supabase Free have usage/resource limits. Check the providers' current quotas and monitor usage; free-tier terms can change.
- Render cold starts and resource limits may affect availability and long-running training operations.

## Security rules and repository hygiene

- `firestore.rules` denies direct browser/client access. The backend authenticates with Google credentials and accesses Firestore through its REST API.
- `storage.rules` is not used by the current application; photographs and model artifacts use the private Supabase bucket.
- Keep `.env`, `.env.local`, `backend/.env`, service-account JSON files, Supabase Secret keys, raw laboratory photographs, and private experimental records out of Git.
- Firebase Web App configuration is expected to be present in browser builds, but it is not a substitute for server-side authorization.
- Never set the Supabase bucket to public. The backend alone should use the Supabase Secret key.

## License

No license has been added yet. Unless a license is added, the public repository is visible but normal copyright restrictions still apply; public visibility alone does not grant permission to reuse or redistribute the code.
