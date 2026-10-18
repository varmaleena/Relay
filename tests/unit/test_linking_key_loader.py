import base64
from unittest.mock import Mock

import pytest

from packages.linking.runtime import load_cloud_key


def test_immutable_key_version_is_loaded_without_exposing_payload():
    session = Mock()
    session.get.return_value.json.return_value = {
        "payload": {"data": base64.b64encode(b"x" * 32).decode()}
    }
    resource = "projects/work-511514/secrets/relay-link-hmac/versions/1"
    assert load_cloud_key(resource, session=session) == b"x" * 32
    assert session.get.call_args.kwargs["timeout"] == 5


@pytest.mark.parametrize(
    "value",
    ["", "latest", "projects/work-511514/secrets/key/versions/latest", "https://evil.invalid/key"],
)
def test_invalid_key_target_does_not_issue_request(value):
    session = Mock()
    with pytest.raises(ValueError):
        load_cloud_key(value, session=session)
    session.get.assert_not_called()


def test_remote_error_and_short_key_remain_static():
    session = Mock()
    session.get.return_value.json.return_value = {"payload": {"data": "eA=="}}
    with pytest.raises(ValueError, match="^Linking key unavailable$"):
        load_cloud_key("projects/work-511514/secrets/key/versions/1", session=session)
