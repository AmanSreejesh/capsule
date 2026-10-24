import pytest

from capsule_cli import node_runtime
from capsule_cli.node_runtime import check_node


@pytest.mark.parametrize(
    "declared, installed, compatible",
    [
        ("20", "20.11.1", True),
        ("v20.2.0", "20.11.1", True),
        ("20.2.0", "21.0.0", False),
        (">=18 <21", "20.11.1", True),
        (">=18 <20", "20.0.0", False),
        ("^20.2.0", "20.12.0", True),
        ("^20.2.0", "21.0.0", False),
        ("~20.2.0", "20.2.9", True),
        ("~20.2.0", "20.3.0", False),
    ],
)
def test_compatibility(declared, installed, compatible):
    assert check_node(declared, installed).compatible is compatible


def test_missing_node_is_failure(monkeypatch):
    monkeypatch.setattr(node_runtime, "installed_node_version", lambda: None)
    result = check_node("20")
    assert result.compatible is False
    assert result.installed is None


def test_named_lts_is_warning_not_failure():
    assert check_node("lts/iron", "20.1.0").compatible is None


def test_partially_understood_range_is_not_misreported():
    result = check_node(">=18 || >=22", "20.1.0")
    assert result.compatible is None
    assert "not understood" in result.explanation
