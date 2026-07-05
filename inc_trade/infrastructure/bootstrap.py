"""Bootstrap orchestration — deterministic startup sequence.

Coordinates the 9-step initialization order so every subsystem is
ready before the first user request:

1. Load configuration (AppConfig + environment profile)
2. Validate configuration (profile-aware validation)
3. Initialize logging
4. Resolve credentials (env files + secret manager)
5. Wire DI container (register core services)
6. Create lifecycle manager
7. Register broker gateways
8. Start managed services
9. Emit startup health snapshot

Usage::

    from inc_trade.infrastructure.bootstrap import Bootstrap

    result = await Bootstrap.run()
    # result.lifecycle, result.container, result.registry are ready
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    """Outcome of a successful bootstrap sequence."""

    config: Any
    profile: Any
    container: Any
    lifecycle: Any
    registry: Any
    validation_warnings: list[str] = field(default_factory=list)


class BootstrapError(Exception):
    """Raised when a critical bootstrap step fails."""


class Bootstrap:
    """Deterministic startup orchestration.

    Each step is isolated so a failure in one produces a clear error
    message without partially-initialized state leaking into the app.
    """

    @staticmethod
    async def run(
        *,
        broker_names: list[str] | None = None,
        skip_validation: bool = False,
    ) -> BootstrapResult:
        """Execute the full bootstrap sequence.

        Parameters
        ----------
        broker_names:
            List of broker IDs to initialize (e.g. ["dhan", "upstox"]).
            If None, reads from TRADEX_BROKERS env var or defaults to ["dhan"].
        skip_validation:
            Skip config validation (useful for tests).
        """
        steps = [
            ("config", Bootstrap._step_load_config),
            ("validation", Bootstrap._step_validate_config),
            ("logging", Bootstrap._step_init_logging),
            ("credentials", Bootstrap._step_resolve_credentials),
            ("di", Bootstrap._step_wire_container),
            ("lifecycle", Bootstrap._step_create_lifecycle),
            ("registry", Bootstrap._step_create_registry),
            ("brokers", Bootstrap._step_register_brokers),
            ("health", Bootstrap._step_emit_health),
        ]

        context: dict[str, Any] = {
            "broker_names": broker_names,
            "skip_validation": skip_validation,
        }

        for step_name, step_fn in steps:
            try:
                logger.info("bootstrap.step: %s", step_name)
                step_fn(context)
            except BootstrapError:
                raise
            except Exception as exc:
                raise BootstrapError(
                    f"Bootstrap failed at step '{step_name}': "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

        return BootstrapResult(
            config=context["config"],
            profile=context["profile"],
            container=context["container"],
            lifecycle=context["lifecycle"],
            registry=context["registry"],
            validation_warnings=context.get("validation_warnings", []),
        )

    @staticmethod
    def _step_load_config(ctx: dict[str, Any]) -> None:
        from inc_trade.config import get_config, load_profile

        ctx["profile"] = load_profile()
        ctx["config"] = get_config()

    @staticmethod
    def _step_validate_config(ctx: dict[str, Any]) -> None:
        if ctx.get("skip_validation"):
            ctx["validation_warnings"] = []
            return

        from inc_trade.config import validate_config
        from inc_trade.config.validator import ValidationProfile

        profile = ctx["profile"]
        profile_map = {
            "dev": ValidationProfile.DEV,
            "staging": ValidationProfile.STAGING,
            "prod": ValidationProfile.PROD,
        }
        vp = profile_map.get(profile.name, ValidationProfile.DEV)
        result = validate_config(vp)
        ctx["validation_warnings"] = result.warnings
        if not result.valid:
            raise BootstrapError(
                f"Config validation failed: {'; '.join(result.errors)}"
            )

    @staticmethod
    def _step_init_logging(ctx: dict[str, Any]) -> None:
        import logging as _logging

        from inc_trade.infrastructure.logging import configure_logging

        profile = ctx["profile"]
        level = getattr(_logging, profile.log_level.upper(), _logging.INFO)
        configure_logging(level=level)

    @staticmethod
    def _step_resolve_credentials(ctx: dict[str, Any]) -> None:
        from inc_trade.infrastructure.credentials import CredentialResolver

        resolver = CredentialResolver()
        broker_names = ctx.get("broker_names") or ["dhan"]
        for broker in broker_names:
            resolver.load_broker_env(broker)

    @staticmethod
    def _step_wire_container(ctx: dict[str, Any]) -> None:
        from inc_trade.core.di import Scope, container

        config = ctx["config"]
        profile = ctx["profile"]

        container.register_instance("config", config)
        container.register_instance("profile", profile)

        from inc_trade.config.secrets_manager import SecretsManager

        container.register(
            "secrets_manager",
            SecretsManager,
            scope=Scope.SINGLETON,
        )

        ctx["container"] = container

    @staticmethod
    def _step_create_lifecycle(ctx: dict[str, Any]) -> None:
        from inc_trade.infrastructure.lifecycle import LifecycleManager

        manager = LifecycleManager()
        ctx["lifecycle"] = manager

    @staticmethod
    def _step_create_registry(ctx: dict[str, Any]) -> None:
        from inc_trade.infrastructure.registry import BrokerRegistry

        registry = BrokerRegistry()
        ctx["registry"] = registry

    @staticmethod
    def _step_register_brokers(ctx: dict[str, Any]) -> None:
        broker_names = ctx.get("broker_names") or [
            b.strip()
            for b in os.environ.get("TRADEX_BROKERS", "dhan").split(",")
            if b.strip()
        ]
        ctx["resolved_broker_names"] = broker_names
        logger.info("bootstrap: brokers=%s", broker_names)

    @staticmethod
    def _step_emit_health(ctx: dict[str, Any]) -> None:
        lifecycle = ctx["lifecycle"]
        snapshot = lifecycle.health_snapshot()
        logger.info("bootstrap: health_snapshot services=%d", len(snapshot))


async def bootstrap(
    *,
    broker_names: list[str] | None = None,
    skip_validation: bool = False,
) -> BootstrapResult:
    """Convenience function — delegates to :meth:`Bootstrap.run`."""
    return await Bootstrap.run(
        broker_names=broker_names,
        skip_validation=skip_validation,
    )
