from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from brokers.common.contracts.module_test_suite import ModuleTestSuite


class ApiModuleTestSuite(ModuleTestSuite):
    def __init__(self) -> None:
        super().__init__(Path(__file__).resolve().parent)


def run(pytest_args: Iterable[str] | None = None) -> int:
    return ApiModuleTestSuite().run_all(pytest_args=pytest_args)


if __name__ == "__main__":
    raise SystemExit(run())
