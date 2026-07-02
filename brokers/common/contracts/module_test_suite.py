from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class ModuleTestSuite:
    path: str | Path
    default_args: tuple[str, ...] = ()

    @property
    def test_path(self) -> Path:
        return Path(self.path)

    def run(
        self,
        *,
        pytest_args: Iterable[str] | None = None,
        addopts: Iterable[str] | None = None,
    ) -> int:
        args = [
            str(self.test_path),
            *self.default_args,
            *(addopts or ()),
            *(pytest_args or ()),
        ]
        return pytest.main(args)

    def run_unit(
        self,
        *,
        pytest_args: Iterable[str] | None = None,
        addopts: Iterable[str] | None = None,
    ) -> int:
        return self.run(
            pytest_args=(
                str(self.test_path / "unit"),
                "-m",
                "not integration and not sandbox and not live_readonly",
                *(pytest_args or ()),
            ),
            addopts=addopts,
        )

    def run_contract(
        self,
        *,
        pytest_args: Iterable[str] | None = None,
        addopts: Iterable[str] | None = None,
    ) -> int:
        return self.run(
            pytest_args=(str(self.test_path / "contract"), *(pytest_args or ())),
            addopts=addopts,
        )

    def run_integration(
        self,
        *,
        pytest_args: Iterable[str] | None = None,
        addopts: Iterable[str] | None = None,
    ) -> int:
        return self.run(
            pytest_args=(str(self.test_path / "integration"), *(pytest_args or ())),
            addopts=addopts,
        )

    def run_all(
        self,
        *,
        pytest_args: Iterable[str] | None = None,
        addopts: Iterable[str] | None = None,
    ) -> int:
        return self.run(pytest_args=pytest_args, addopts=addopts)


def run_module_tests(path: str | Path, *, pytest_args: Iterable[str] | None = None) -> int:
    return ModuleTestSuite(path).run(pytest_args=pytest_args)
