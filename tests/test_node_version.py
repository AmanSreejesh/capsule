import json
from pathlib import Path

import pytest

from capsule_cli.node_version import NodeVersion, find_node_version


def write(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text, encoding="utf-8")


def write_package_json(root: Path, data: dict) -> None:
    write(root, "package.json", json.dumps(data))


@pytest.mark.parametrize(
    "name, text, expected",
    [
        (".nvmrc", "20.11.1\n", "20.11.1"),
        (".nvmrc", "v20\n", "v20"),
        (".nvmrc", "lts/iron\n", "lts/iron"),
        (".node-version", "22.3.0", "22.3.0"),
        (".tool-versions", "python 3.12.0\nnodejs 20.11.1\n", "20.11.1"),
        (".tool-versions", "node 22.3.0 20.11.1\n", "22.3.0"),
    ],
)
def test_version_files_are_read_as_written(tmp_path, name, text, expected):
    write(tmp_path, name, text)
    assert find_node_version(tmp_path) == NodeVersion(expected, name)


def test_comments_and_blank_lines_are_skipped(tmp_path):
    write(tmp_path, ".nvmrc", "\n# pinned for the build server\n  20.11.1  # current LTS\n")
    assert find_node_version(tmp_path) == NodeVersion("20.11.1", ".nvmrc")


def test_volta_field(tmp_path):
    write_package_json(tmp_path, {"volta": {"node": "20.11.1"}})
    assert find_node_version(tmp_path) == NodeVersion("20.11.1", "package.json (volta.node)")


def test_engines_field(tmp_path):
    write_package_json(tmp_path, {"engines": {"node": ">=18 <21"}})
    assert find_node_version(tmp_path) == NodeVersion(">=18 <21", "package.json (engines.node)")


def test_package_json_with_byte_order_mark(tmp_path):
    (tmp_path / "package.json").write_bytes(b'\xef\xbb\xbf{"engines": {"node": ">=20"}}')
    assert find_node_version(tmp_path) == NodeVersion(">=20", "package.json (engines.node)")


def test_priority_order(tmp_path):
    write(tmp_path, ".nvmrc", "1")
    write(tmp_path, ".node-version", "2")
    write(tmp_path, ".tool-versions", "nodejs 3")
    write_package_json(tmp_path, {"volta": {"node": "4"}, "engines": {"node": "5"}})

    # Remove the winning file each time; the next one in priority order should take over.
    assert find_node_version(tmp_path) == NodeVersion("1", ".nvmrc")
    (tmp_path / ".nvmrc").unlink()
    assert find_node_version(tmp_path) == NodeVersion("2", ".node-version")
    (tmp_path / ".node-version").unlink()
    assert find_node_version(tmp_path) == NodeVersion("3", ".tool-versions")
    (tmp_path / ".tool-versions").unlink()
    assert find_node_version(tmp_path) == NodeVersion("4", "package.json (volta.node)")
    write_package_json(tmp_path, {"engines": {"node": "5"}})
    assert find_node_version(tmp_path) == NodeVersion("5", "package.json (engines.node)")


def test_nothing_declared(tmp_path):
    assert find_node_version(tmp_path) is None


@pytest.mark.parametrize(
    "name, text",
    [
        (".nvmrc", "\n# only a comment\n"),
        (".tool-versions", "python 3.12.0\nnodejs\n"),
    ],
)
def test_files_without_a_version_fall_through(tmp_path, name, text):
    write(tmp_path, name, text)
    write_package_json(tmp_path, {"engines": {"node": ">=20"}})
    assert find_node_version(tmp_path) == NodeVersion(">=20", "package.json (engines.node)")


@pytest.mark.parametrize(
    "text",
    [
        "{ not json",
        "[]",
        '{"engines": "node 20"}',
        '{"engines": {"node": 20}}',
    ],
)
def test_unusable_package_json_declares_nothing(tmp_path, text):
    write(tmp_path, "package.json", text)
    assert find_node_version(tmp_path) is None
