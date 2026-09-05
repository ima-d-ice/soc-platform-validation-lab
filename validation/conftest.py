"""Shared pytest fixtures for the virtual SoC validation harness.

Golden flow (pre-silicon):

    create SoC config -> boot firmware -> execute workload ->
    capture trace -> compare expected -> generate report
"""
from __future__ import annotations

import pathlib

import pytest

from soc.soc import SoC, load_config

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE_CONFIG = ROOT / "configs" / "base.yaml"


@pytest.fixture(scope="function")
def config():
    return load_config(BASE_CONFIG)


@pytest.fixture(scope="function")
def soc(config):
    """Booted SoC on the golden base config."""
    s = SoC(config)
    s.boot()
    return s


@pytest.fixture(scope="function")
def fresh_soc(config):
    """Unbooted SoC for boot-flow tests (caller must boot)."""
    return SoC(config)
