"""Admin helpers for managing the four private team accounts."""
from __future__ import annotations

import argparse
import os

import firebase_admin
from firebase_admin import auth, credentials


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or remove the private team custom claim.")
    parser.add_argument("emails", nargs="+", help="Email addresses of the four team accounts")
    parser.add_argument("--remove", action="store_true", help="Set teamMember=false instead of granting access")
    args = parser.parse_args()
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if not project_id:
        parser.error("Set FIREBASE_PROJECT_ID before running this command.")
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": project_id})

    for email in args.emails:
        user = auth.get_user_by_email(email)
        claims = dict(user.custom_claims or {})
        claims["teamMember"] = not args.remove
        auth.set_custom_user_claims(user.uid, claims)
        print(f"{'Removed' if args.remove else 'Granted'} teamMember for {email} (UID {user.uid})")
    print("The users must refresh their ID tokens (sign out/in) before the new claim is present.")


if __name__ == "__main__":
    main()
