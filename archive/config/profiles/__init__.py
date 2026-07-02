"""Environment-specific configuration profiles.

Loads profile based on APP_ENV environment variable:
- dev: Relaxed validation, verbose logging, mock brokers allowed
- staging: Strict validation, real brokers, debug endpoints enabled
- prod: Maximum strictness, real brokers, no debug endpoints

Usage::

    from config.profiles import load_profile

    profile = load_profile()  # Loads from APP_ENV or defaults to dev
"""

from config.profiles.base import BaseProfile, EnvironmentProfile
from config.profiles.dev import DevProfile
from config.profiles.prod import ProdProfile
from config.profiles.staging import StagingProfile

__all__ = [
    "BaseProfile",
    "DevProfile",
    "EnvironmentProfile",
    "ProdProfile",
    "StagingProfile",
    "load_profile",
]


def load_profile(profile_name: str | None = None) -> EnvironmentProfile:
    """Load environment profile.

    Args:
        profile_name: Profile name (dev/staging/prod). If None,
            loads from APP_ENV env var or defaults to 'dev'.

    Returns:
        EnvironmentProfile instance for the specified environment.
    """
    import os

    if profile_name is None:
        profile_name = os.environ.get("APP_ENV", "dev")

    profiles = {
        "dev": DevProfile,
        "staging": StagingProfile,
        "prod": ProdProfile,
    }

    profile_class = profiles.get(profile_name)
    if profile_class is None:
        raise ValueError(
            f"Unknown profile '{profile_name}'. Available profiles: {list(profiles.keys())}"
        )

    return profile_class()
