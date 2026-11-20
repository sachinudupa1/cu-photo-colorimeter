"""Lazy Firebase Admin initialization; Cloud Run uses its attached service account."""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def firebase_app():
    import firebase_admin
    from firebase_admin import credentials
    from . import settings

    settings.validate_firebase_config()
    try:
        app = firebase_admin.get_app()
    except ValueError:
        # On Cloud Run, Application Default Credentials come from the attached
        # service account. Locally, use `gcloud auth application-default login`.
        cred = credentials.ApplicationDefault()
        app = firebase_admin.initialize_app(
            cred,
            {"projectId": settings.PROJECT_ID},
        )
    return app


@lru_cache(maxsize=1)
def firestore_client():
    # Use Firestore REST + ADC to avoid importing grpcio's native cygrpc DLL.
    # This works locally with `gcloud auth application-default login` and on
    # Cloud Run with the service's attached runtime identity.
    from .firestore_rest import FirestoreRestClient
    return FirestoreRestClient()


def storage_bucket():
    from firebase_admin import storage
    return storage.bucket(app=firebase_app())


def auth_verify_id_token(token: str) -> dict:
    from firebase_admin import auth
    # Revocation checking requires the runtime identity to have the read-only
    # Firebase Authentication Viewer role (firebaseauth.users.get).
    return auth.verify_id_token(token, app=firebase_app(), check_revoked=True)


def app_check_verify_token(token: str) -> dict:
    from firebase_admin import app_check
    return app_check.verify_token(token, app=firebase_app())
