"""Explicit loopback Firebase Auth emulator adapter, never a deployed auth fallback."""

import asyncio
import os
import threading
from typing import Any

from packages.common.auth import AuthenticationError, actor_from_verified_claims
from packages.safety import Actor


class EmulatorIdentityVerifier:
    def __init__(self, project_id: str, host: str) -> None:
        if not project_id.startswith("demo-") or host not in {"127.0.0.1:9099", "localhost:9099"}:
            raise ValueError("Firebase emulator requires a demo project and loopback host")
        if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST") != host:
            raise ValueError("Explicit Firebase Auth emulator environment required")
        self.project_id = project_id
        self.host = host
        self._app: Any = None
        self._lock = threading.Lock()

    def _verify(self, token: str) -> Actor:
        import firebase_admin
        from firebase_admin import auth, credentials
        from google.auth.credentials import AnonymousCredentials

        class EmulatorCredential(credentials.Base):
            def get_credential(self) -> AnonymousCredentials:
                return AnonymousCredentials()

        try:
            if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST") != self.host:
                raise AuthenticationError("unauthenticated")
            with self._lock:
                if self._app is None:
                    name = "relay-emulator-" + self.project_id
                    try:
                        self._app = firebase_admin.get_app(name)
                    except ValueError:
                        self._app = firebase_admin.initialize_app(
                            EmulatorCredential(), options={"projectId": self.project_id}, name=name
                        )
            claims = auth.verify_id_token(token, app=self._app, check_revoked=True)
            return actor_from_verified_claims(claims)
        except Exception as error:
            raise AuthenticationError("unauthenticated") from error

    async def verify(self, id_token: str, app_check_token: str) -> Actor:
        # Firebase offers no App Check emulator. Only this local demo adapter omits
        # that check; the deployed FirebaseIdentityVerifier still requires it.
        if not id_token or len(id_token) > 8192:
            raise AuthenticationError("unauthenticated")
        return await asyncio.wait_for(asyncio.to_thread(self._verify, id_token), timeout=10)
