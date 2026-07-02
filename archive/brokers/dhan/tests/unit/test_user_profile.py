"""Unit tests for UserProfileAdapter."""

from brokers.dhan.user_profile import UserProfileAdapter


def test_get_user_profile(fake_client):
    """Verify GET /userprofile response parsing."""
    fake_client.set_response(
        "GET",
        "/userprofile",
        {
            "data": {
                "tokenValid": True,
                "activeSegments": ["NSE_EQ", "NFO", "MCX"],
                "ddpiStatus": "ACTIVATED",
                "mtfEnabled": False,
                "dataApiSubscription": "FREE",
                "userConfigurations": {
                    "defaultProductType": "INTRADAY",
                    "defaultValidity": "DAY",
                },
            }
        },
    )
    adapter = UserProfileAdapter(fake_client)
    profile = adapter.get_profile()

    assert profile.token_valid is True
    assert profile.active_segments == ["NSE_EQ", "NFO", "MCX"]
    assert profile.ddpi_status == "ACTIVATED"
    assert profile.mtf_enabled is False
    assert profile.data_api_subscription == "FREE"
    assert profile.user_configurations["defaultProductType"] == "INTRADAY"


def test_get_user_profile_token_valid(fake_client):
    """Verify token_valid field."""
    fake_client.set_response(
        "GET",
        "/userprofile",
        {
            "data": {
                "tokenValid": False,
                "activeSegments": [],
                "ddpiStatus": "PENDING",
                "mtfEnabled": False,
                "dataApiSubscription": "NONE",
                "userConfigurations": {},
            }
        },
    )
    adapter = UserProfileAdapter(fake_client)
    profile = adapter.get_profile()

    assert profile.token_valid is False


def test_get_user_profile_ddpi_status(fake_client):
    """Verify DDPI status parsing."""
    fake_client.set_response(
        "GET",
        "/userprofile",
        {
            "data": {
                "tokenValid": True,
                "activeSegments": ["NSE_EQ"],
                "ddpiStatus": "NOT_ACTIVATED",
                "mtfEnabled": False,
                "dataApiSubscription": "FREE",
                "userConfigurations": {},
            }
        },
    )
    adapter = UserProfileAdapter(fake_client)
    profile = adapter.get_profile()

    assert profile.ddpi_status == "NOT_ACTIVATED"


def test_get_user_profile_mtf_enabled(fake_client):
    """Verify MTF enabled flag."""
    fake_client.set_response(
        "GET",
        "/userprofile",
        {
            "data": {
                "tokenValid": True,
                "activeSegments": ["NSE_EQ"],
                "ddpiStatus": "ACTIVATED",
                "mtfEnabled": True,
                "dataApiSubscription": "PAID",
                "userConfigurations": {},
            }
        },
    )
    adapter = UserProfileAdapter(fake_client)
    profile = adapter.get_profile()

    assert profile.mtf_enabled is True
