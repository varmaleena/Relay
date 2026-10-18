"""Fixture provisioning cannot adopt accounts or rotate stored credentials."""

from types import SimpleNamespace

import pytest

from scripts.seed_staff import FixtureError, load_credentials, seed, validate_target


class FakeAuth:
    class UserNotFoundError(Exception):
        pass

    def __init__(self):
        self.users = {}
        self.created = []

    def get_user_by_email(self, email, *, app):
        for user in self.users.values():
            if user.email == email:
                return user
        raise self.UserNotFoundError()

    def get_user(self, uid, *, app):
        if uid not in self.users:
            raise self.UserNotFoundError()
        return self.users[uid]

    def create_user(self, *, uid, email, password, email_verified, app):
        self.created.append(uid)
        self.users[uid] = SimpleNamespace(uid=uid, email=email, custom_claims=None, disabled=False)
        return self.users[uid]

    def set_custom_user_claims(self, uid, claims, *, app):
        self.users[uid].custom_claims = claims


def test_target_is_explicit_and_loopback_only(monkeypatch):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    for project, emulator, apply in [
        ("other", False, True),
        ("work-511514", False, False),
        ("demo-relay-local", False, True),
        ("demo-relay-local", True, False),
    ]:
        with pytest.raises(FixtureError):
            validate_target(project, emulator=emulator, apply=apply)
    validate_target("work-511514", emulator=False, apply=True)
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "remote:9099")
    with pytest.raises(FixtureError):
        validate_target("demo-relay-local", emulator=True, apply=False)
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    validate_target("demo-relay-local", emulator=True, apply=False)
    with pytest.raises(FixtureError):
        validate_target("work-511514", emulator=False, apply=True)


def test_local_credentials_and_account_rerun_are_unchanged(tmp_path, capsys):
    data = load_credentials("demo-relay-local", tmp_path / "private")
    path = tmp_path / "private/staff-demo-relay-local.json"
    original = path.read_bytes()
    auth = FakeAuth()
    assert seed(auth, data, app=None) == {"created": 3, "existing": 0}
    again = load_credentials("demo-relay-local", tmp_path / "private")
    assert again == data and path.read_bytes() == original
    assert seed(auth, again, app=None) == {"created": 0, "existing": 3}
    assert len(auth.created) == 3
    output = capsys.readouterr()
    for entry in data["users"].values():
        assert entry["password"] not in output.out + output.err


@pytest.mark.parametrize("mismatch", ["uid", "claims", "disabled", "uid_collision"])
def test_existing_nonfixture_accounts_never_adopted(tmp_path, mismatch):
    data = load_credentials("demo-relay-local", tmp_path)
    first = data["users"]["mock-bank"]
    auth = FakeAuth()
    user = SimpleNamespace(
        uid=first["uid"],
        email=first["email"],
        disabled=False,
        custom_claims={"role": "receiver", "orgId": "mock-bank", "syntheticDemo": True},
    )
    if mismatch == "uid":
        user.uid = "real-user"
    elif mismatch == "claims":
        user.custom_claims = {"role": "admin"}
    elif mismatch == "disabled":
        user.disabled = True
    else:
        user.email = "unrelated@example.invalid"
    auth.users[user.uid] = user
    with pytest.raises(FixtureError):
        seed(auth, data, app=None)
    assert auth.created == []
    assert auth.users[user.uid] is user


def test_corrupt_credentials_refuse_overwrite(tmp_path):
    path = tmp_path / "staff-demo-relay-local.json"
    path.write_text("invalid", encoding="utf-8")
    with pytest.raises(FixtureError):
        load_credentials("demo-relay-local", tmp_path)
    assert path.read_text() == "invalid"
