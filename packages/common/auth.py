"""Firebase identity/App Check verification with no local token bypass."""

import asyncio
import threading
from collections.abc import Mapping
from typing import Any, Protocol

from packages.safety import Actor


class AuthenticationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def actor_from_verified_claims(claims: Mapping[str, Any]) -> Actor:
    """Accept only claims returned by a cryptographic verifier, never JSON headers."""
    uid = claims.get("uid") or claims.get("sub")
    role = claims.get("role")
    firebase = claims.get("firebase", {})
    if (
        role is None
        and isinstance(firebase, dict)
        and firebase.get("sign_in_provider") == "anonymous"
    ):
        role = "victim"
    org_id = claims.get("orgId")
    if (
        not isinstance(uid, str)
        or not uid
        or len(uid) > 128
        or role not in {"victim", "receiver", "reviewer", "admin"}
    ):
        raise AuthenticationError("unauthenticated")
    if role in {"receiver", "reviewer"} and (not isinstance(org_id, str) or not org_id):
        raise AuthenticationError("forbidden")
    if org_id is not None and not isinstance(org_id, str):
        raise AuthenticationError("unauthenticated")
    return Actor(uid, role, org_id)


class IdentityVerifier(Protocol):
    async def verify(self, id_token: str, app_check_token: str) -> Actor: ...


class FirebaseIdentityVerifier:
    """Admin SDK production verifier; tests inject a separate explicit test object."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self._app: Any = None
        self._lock = threading.Lock()

    def _verify(self, id_token: str, app_check_token: str) -> Actor:
        if not self.project_id or not id_token:
            raise AuthenticationError("unauthenticated")
        if not app_check_token:
            raise AuthenticationError("app_check_failed")
        import firebase_admin
        from firebase_admin import app_check, auth

        try:
            with self._lock:
                if self._app is None:
                    name = "relay-" + self.project_id
                    try:
                        self._app = firebase_admin.get_app(name)
                    except ValueError:
                        self._app = firebase_admin.initialize_app(
                            options={"projectId": self.project_id}, name=name
                        )
            claims = auth.verify_id_token(id_token, app=self._app, check_revoked=True)
        except Exception as exc:
            raise AuthenticationError("unauthenticated") from exc
        try:
            app_check.verify_token(app_check_token, app=self._app)
        except Exception as exc:
            raise AuthenticationError("app_check_failed") from exc
        return actor_from_verified_claims(claims)

    async def verify(self, id_token: str, app_check_token: str) -> Actor:
        if len(id_token) > 8192 or len(app_check_token) > 8192:
            raise AuthenticationError("unauthenticated")
        return await asyncio.wait_for(
            asyncio.to_thread(self._verify, id_token, app_check_token), timeout=10
        )
