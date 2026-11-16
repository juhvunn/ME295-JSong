"""Quick suite by default; `pytest --full` also runs tests marked slow (run it before commits)."""
import pytest


def pytest_addoption(parser):
    parser.addoption("--full", action="store_true", help="also run tests marked slow (full 12-simulation runs etc.)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--full"):
        return
    skip = pytest.mark.skip(reason="slow: run with --full")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
