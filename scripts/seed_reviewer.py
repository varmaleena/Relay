"""Provision explicit synthetic Firebase reviewer fixtures; credentials stay local."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

PROJECTS = {"demo-relay-local", "work-511514"}
ORG_EMAILS = {"relay-review-team": "reviewer@relay.example.invalid"}
ROOT = Path(__file__).resolve().parents[1]


class FixtureError(RuntimeError):
    """A safe, static operator error without remote payloads or credentials."""


def validate_target(project: str, *, emulator: bool, apply: bool) -> None:
    if project not in PROJECTS:
        raise FixtureError("Project is not an approved synthetic fixture target")
    host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST")
    if emulator:
        if project != "demo-relay-local" or host != "127.0.0.1:9099":
            raise FixtureError("Emulator requires demo project and explicit loopback port 9099")
    elif project != "work-511514" or not apply or host:
        raise FixtureError("Cloud fixture creation requires --apply and no emulator environment")


def _restrict(path: Path) -> None:
    if os.name == "nt":
        identity = os.environ.get("USERDOMAIN", "")
        identity = (identity + "\\" if identity else "") + getpass.getuser()
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{identity}:(F)"],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise FixtureError("Could not restrict local fixture credential permissions")
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def load_credentials(project: str, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise FixtureError("Credential directory must not be a symbolic link")
    _restrict(directory)
    path = directory / f"reviewer-{project}.json"
    if path.is_symlink():
        raise FixtureError("Credential file must not be a symbolic link")
    if path.exists():
        _restrict(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise FixtureError(
                "Existing fixture credentials are invalid; refusing overwrite"
            ) from exc
    else:
        payload = {
            "project": project,
            "schemaVersion": 1,
            "users": {
                org: {
                    "uid": "synthetic_" + secrets.token_hex(16),
                    "email": email,
                    "password": secrets.token_urlsafe(36),
                }
                for org, email in ORG_EMAILS.items()
            },
        }
        # Parent is private before creation; O_EXCL prevents accidental credential rotation.
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                _restrict(path)
                json.dump(payload, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as exc:
            raise FixtureError("Concurrent credential creation; rerun without overwriting") from exc
    try:
        if payload["project"] != project or payload["schemaVersion"] != 1:
            raise ValueError("target mismatch")
        if set(payload["users"]) != set(ORG_EMAILS):
            raise ValueError("users mismatch")
        for org, email in ORG_EMAILS.items():
            entry = payload["users"][org]
            if entry["email"] != email:
                raise ValueError("email mismatch")
            if not isinstance(entry["uid"], str) or not entry["uid"].startswith("synthetic_"):
                raise ValueError("uid mismatch")
            if len(entry["uid"]) != 42:
                raise ValueError("uid length mismatch")
            if not isinstance(entry["password"], str) or not 40 <= len(entry["password"]) <= 128:
                raise ValueError("password length mismatch")
    except (ValueError, KeyError, TypeError) as exc:
        raise FixtureError("Existing fixture credentials do not match this target") from exc
    return payload


def seed(auth: Any, credentials: dict[str, Any], *, app: Any) -> dict[str, int]:
    created = existing = 0
    for org, entry in credentials["users"].items():
        expected = {"role": "reviewer", "orgId": org, "syntheticDemo": True}
        try:
            user = auth.get_user_by_email(entry["email"], app=app)
        except auth.UserNotFoundError:
            try:
                # Also refuse an existing UID with a different email.
                auth.get_user(entry["uid"], app=app)
            except auth.UserNotFoundError:
                user = auth.create_user(
                    uid=entry["uid"],
                    email=entry["email"],
                    password=entry["password"],
                    email_verified=True,
                    app=app,
                )
                auth.set_custom_user_claims(user.uid, expected, app=app)
                created += 1
                continue
            raise FixtureError("Stored fixture UID belongs to another account") from None
        if (
            user.uid != entry["uid"]
            or user.email != entry["email"]
            or user.custom_claims != expected
            or user.disabled
        ):
            raise FixtureError("Existing account is not the matching synthetic fixture")
        existing += 1
    return {"created": created, "existing": existing}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--emulator", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        validate_target(args.project, emulator=args.emulator, apply=args.apply)
        credentials = load_credentials(args.project, ROOT / ".local" / "reviewer-auth")
        import firebase_admin
        from firebase_admin import auth
        from firebase_admin import credentials as firebase_credentials
        from google.auth.credentials import AnonymousCredentials

        if args.emulator:

            class EmulatorCredential(firebase_credentials.Base):
                def get_credential(self):
                    return AnonymousCredentials()

            credential = EmulatorCredential()
        else:
            credential = firebase_credentials.ApplicationDefault()
        app = firebase_admin.initialize_app(
            credential, {"projectId": args.project}, name="relay-synthetic-reviewer"
        )
        try:
            counts = seed(auth, credentials, app=app)
        finally:
            firebase_admin.delete_app(app)
        print(json.dumps(counts))
    except Exception:
        # Provider errors can contain account details; do not print their payloads.
        parser.exit(1, "Reviewer fixture provisioning refused or failed; no credentials printed.\n")


if __name__ == "__main__":
    main()
