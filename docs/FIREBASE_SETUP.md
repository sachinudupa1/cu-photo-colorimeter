# Firebase setup — Cu-Photo-Colorimeter

This guide covers only the Firebase services used by the current no-billing architecture. The project uses **Firebase Spark** for Authentication, Cloud Firestore, and Firebase Hosting. It does **not** use Firebase Storage or Cloud Run. Photographs and model artifacts are stored in a private Supabase Storage bucket, and the Python API is planned for Render. See the root `README.md` for the full architecture and Render/Supabase deployment plan.

> **Billing note:** Do not upgrade this project to Blaze for this setup. Do not enable Cloud Run or Firebase Storage. Those services are not part of the current architecture. Firebase Spark quotas still apply; monitor usage in Firebase Console.

## A. Existing Firebase project

The current project ID is `cu-photo-colorimeter`. Keep using this project; do not create a second project.

The Firebase resources used by the application are:

- **Authentication:** Email/Password sign-in.
- **Cloud Firestore:** one `(default)` database with two primary collections: `training_data` and `testing_data`.
- **Firebase Hosting:** two Hosting sites, one for the private Training Console and one for the public Presentation Site.

The existing Firestore database location is already selected. Firestore database locations cannot be changed after creation, so do not recreate the database merely to follow a different example region.

## B. Authentication and team access

1. In Firebase Console, open **Authentication → Sign-in method** and ensure **Email/Password** is enabled.
2. Create accounts for the authorised team members under **Authentication → Users**. The Training Console has no public sign-up flow.
3. Add the deployed Training Console domain to **Authentication → Settings → Authorized domains** if Firebase does not already list it.
4. Only accounts granted the `teamMember: true` Firebase custom claim can use private team API routes. Merely creating an Authentication user does not grant laboratory access.

To grant the claim from a trusted local administrator session, open PowerShell at the repository root and run:

```powershell
$env:FIREBASE_PROJECT_ID = "cu-photo-colorimeter"
.\.venv\Scripts\python.exe scripts/set_team_claims.py teammate1@example.com teammate2@example.com
```

The command requires Google Application Default Credentials (ADC) for an account that has sufficient Firebase Authentication user-management permissions. After a claim is granted or removed, the affected teammate must sign out and sign in again to refresh the ID token.

To remove a team claim:

```powershell
$env:FIREBASE_PROJECT_ID = "cu-photo-colorimeter"
.\.venv\Scripts\python.exe scripts/set_team_claims.py --remove teammate@example.com
```

Do not share passwords, recovery codes, ADC files, service-account JSON files, or private keys. Send team credentials through a private channel.

## C. Firestore security rules and data model

The repository's `firestore.rules` denies all direct browser/client reads and writes. Both websites call the FastAPI backend; they do not query Firestore directly. The backend verifies Firebase ID tokens and checks the `teamMember` claim on private routes. The backend accesses Firestore through the Firestore REST API using Google credentials (ADC locally; a dedicated service-account credential on Render).

The two primary Firestore collections are:

1. `training_data` — independently prepared blanks, standards, validation samples, and resolution replicates. Each document records sample/session metadata, concentration when applicable, reference colorimeter measurements, verification status, and private Supabase object paths.
2. `testing_data` — presentation/live prediction records, including predicted concentration, warnings, model version, and image paths. A teammate may add the reference concentration and colorimeter reading after the prediction is saved. Such records are not automatically added to training data.

Do not weaken the rules to `allow read, write: if true` or to a broad authenticated-user rule. The backend performs the authorization checks. Test any future rule changes before deployment.

To deploy only the Firestore rules:

```powershell
firebase deploy --only firestore:rules --project cu-photo-colorimeter
```

**Do not run `firebase deploy --only storage`.** Firebase Storage is not used by the current application. The root `storage.rules` file is retained as a legacy reference and is not deployed by the current `firebase.json`.

## D. Register the two Firebase Web Apps

In **Project settings → General → Your apps**, ensure the two Web Apps exist:

- `cu-photo-training-console`
- `cu-photo-presentation-site`

Each app has a different `appId`. Both use the same Firebase project ID, auth domain and Web API key. Copy the matching Web App configuration into the corresponding local frontend environment file.

Create the files if they do not already exist:

```powershell
Copy-Item apps/training-console/.env.example apps/training-console/.env.local
Copy-Item apps/presentation-site/.env.example apps/presentation-site/.env.local
```

Set the `VITE_FIREBASE_*` values for the correct Web App in each file. For local development, set the API URL in **both** files to:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8080/api
```

For production builds, replace that value in both files with the actual Render API URL, for example:

```dotenv
VITE_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com/api
```

Firebase Web App configuration values are intended for browser use. They are not server passwords. Never place the Supabase Secret key or a service-account JSON file in a frontend `.env.local` file or any `VITE_` variable.

## E. Configure two Firebase Hosting sites

The root `firebase.json` defines two Hosting targets:

- `lab` → `apps/training-console/dist`
- `presentation` → `apps/presentation-site/dist`

There are **no Cloud Run rewrites**. Each frontend calls the Render API using its `VITE_API_BASE_URL` setting. The public API must allow the exact two Firebase Hosting origins in its Render `ALLOWED_ORIGINS` environment variable.

Install and authenticate the Firebase CLI if needed:

```powershell
npm install -g firebase-tools
firebase login
```

Create the local Firebase project/target file from the committed example:

```powershell
Copy-Item .firebaserc.example .firebaserc
notepad .firebaserc
```

In `.firebaserc`, replace the placeholder project ID with `cu-photo-colorimeter` and replace the placeholder Hosting site IDs with the exact site IDs created in Firebase Hosting. `.firebaserc` is local configuration and is ignored by Git; do not commit it.

If the two Hosting sites have not yet been created, create them in **Firebase Console → Hosting** first. Record their exact site IDs. Then apply the target mappings (replace the placeholders):

```powershell
firebase target:apply hosting lab YOUR_LAB_HOSTING_SITE_ID --project cu-photo-colorimeter
firebase target:apply hosting presentation YOUR_PRESENTATION_HOSTING_SITE_ID --project cu-photo-colorimeter
```

Build both websites from the repository root:

```powershell
Push-Location apps/training-console
npm ci
npm run build
Pop-Location

Push-Location apps/presentation-site
npm ci
npm run build
Pop-Location
```

Deploy the Firestore rules and the two websites:

```powershell
firebase deploy --only firestore:rules --project cu-photo-colorimeter
firebase deploy --only hosting:lab,hosting:presentation --project cu-photo-colorimeter
```

The Training Console URL is the `lab` site's `https://SITE_ID.web.app` address. It requires an authorised teammate login. The Presentation Site URL is the `presentation` site's `https://SITE_ID.web.app` address and is publicly accessible.

## F. Backend and Supabase configuration are separate

Firebase does not store photographs or model artifacts in the current architecture. The Python backend uses the private Supabase bucket `cu-photo-images` for those objects. Keep `SUPABASE_SECRET_KEY` only in the local `backend/.env` and in the Render service's private environment configuration. Never commit the key or expose it to the browser.

The backend also needs Google credentials to verify Firebase ID tokens and access Firestore REST. Local development uses ADC. For the planned Render deployment, configure a dedicated least-privilege service account using Render's supported secret-file mechanism, or another supported secure workload-identity option. Do not commit the credential JSON. The root `README.md` documents the Render/Supabase deployment plan and its free-tier limitations.

## G. Important operational safeguards

- Keep the Firebase project on Spark; do not link billing or upgrade plans as part of this guide.
- Do not enable Cloud Run or Firebase Storage for the current architecture.
- Keep `.env`, `.env.local`, `backend/.env`, `.firebaserc`, service-account JSON, and private data out of Git.
- Never make the Supabase bucket public. The backend alone uses the Supabase Secret key.
- The training site is private through Firebase Authentication plus the server-side `teamMember` claim; the presentation site is public.
- Do not claim scientific accuracy until real independently prepared laboratory samples have been measured and validated against the laboratory colorimeter.
