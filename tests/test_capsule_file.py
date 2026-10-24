import pytest

from capsule_cli.capsule_file import (
    CapsuleFileError,
    build,
    dumps,
    find_project_root,
    load,
    write_if_changed,
)
from capsule_cli.node_version import NodeVersion
from capsule_cli.scanner import Location, ScanResult


def scan_of(**vars_to_paths: list[str]) -> ScanResult:
    """A ScanResult where each keyword is a var name and its value lists the files reading it."""
    return ScanResult(
        env_vars={
            name: [Location(path, 1) for path in paths] for name, paths in vars_to_paths.items()
        }
    )


NODE = NodeVersion("20", ".nvmrc")


# --- build: combining the scan with the existing file ---


def test_build_from_scratch():
    scan = ScanResult(
        env_vars={
            "B": [Location("src/b.ts", 3), Location("src/a.ts", 9), Location("src/b.ts", 7)],
            "A": [Location("src/a.ts", 1)],
        }
    )
    assert build(scan, NODE, None) == {
        "format": 1,
        "node": {"version": "20", "source": ".nvmrc"},
        "env": {
            "A": {"used_in": ["src/a.ts"]},
            "B": {"used_in": ["src/a.ts", "src/b.ts"]},
        },
    }


def test_no_node_version_is_null():
    assert build(scan_of(), None, None)["node"] is None


def test_human_fields_are_kept_and_used_in_is_refreshed():
    existing = {
        "env": {"A": {"note": "ask #backend", "optional": True, "used_in": ["old/place.ts"]}}
    }
    data = build(scan_of(A=["src/new.ts"]), NODE, existing)
    assert data["env"]["A"] == {"note": "ask #backend", "optional": True, "used_in": ["src/new.ts"]}


def test_var_no_longer_read_is_dropped_with_its_note():
    existing = {"env": {"GONE": {"note": "old", "used_in": ["src/a.ts"]}}}
    assert build(scan_of(), NODE, existing)["env"] == {}


def test_manual_var_is_kept_even_when_not_found():
    existing = {"env": {"FEATURE_X": {"manual": True, "note": "via flag()"}}}
    assert build(scan_of(), NODE, existing)["env"] == {
        "FEATURE_X": {"manual": True, "note": "via flag()", "used_in": []}
    }


def test_manual_var_found_by_scanner_gets_used_in():
    existing = {"env": {"A": {"manual": True}}}
    assert build(scan_of(A=["src/a.ts"]), NODE, existing)["env"]["A"] == {
        "manual": True,
        "used_in": ["src/a.ts"],
    }


def test_other_top_level_fields_are_kept_after_capsules_own():
    existing = {"$comment": "see README", "format": 1, "node": None, "env": {}}
    data = build(scan_of(), NODE, existing)
    assert list(data) == ["format", "node", "env", "$comment"]
    assert data["node"] == {"version": "20", "source": ".nvmrc"}


# --- dumps / write_if_changed: standard formatting ---


def test_dumps_is_sorted_indented_and_ends_with_newline():
    data = build(scan_of(B=["b.js"], A=["a.js"]), NODE, {"env": {"A": {"note": "n"}}})
    assert dumps(data) == (
        "{\n"
        '  "format": 1,\n'
        '  "node": {\n'
        '    "version": "20",\n'
        '    "source": ".nvmrc"\n'
        "  },\n"
        '  "env": {\n'
        '    "A": {\n'
        '      "note": "n",\n'
        '      "used_in": [\n'
        '        "a.js"\n'
        "      ]\n"
        "    },\n"
        '    "B": {\n'
        '      "used_in": [\n'
        '        "b.js"\n'
        "      ]\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def test_same_contents_in_any_order_give_the_same_text():
    first = build(scan_of(A=["a.js"], B=["b.js"]), NODE, {"env": {"A": {"z": 1, "note": "n"}}})
    second = build(scan_of(B=["b.js"], A=["a.js"]), NODE, {"env": {"A": {"note": "n", "z": 1}}})
    assert dumps(first) == dumps(second)


def test_write_if_changed(tmp_path):
    path = tmp_path / "capsule.json"
    data = build(scan_of(A=["a.js"]), NODE, None)

    assert write_if_changed(path, data) is True
    assert write_if_changed(path, data) is False
    assert b"\r\n" not in path.read_bytes()
    assert not list(tmp_path.glob(".capsule.json.*.tmp"))


def test_file_with_windows_line_endings_counts_as_unchanged(tmp_path):
    path = tmp_path / "capsule.json"
    data = build(scan_of(A=["a.js"]), NODE, None)
    path.write_bytes(dumps(data).replace("\n", "\r\n").encode())
    assert write_if_changed(path, data) is False


# --- load: refusing files it can't safely rewrite ---


def test_missing_file_loads_as_none(tmp_path):
    assert load(tmp_path / "capsule.json") is None


def test_valid_file_round_trips(tmp_path):
    path = tmp_path / "capsule.json"
    data = build(scan_of(A=["a.js"]), NODE, {"env": {"A": {"note": "héllo"}}})
    write_if_changed(path, data)
    assert load(path) == data


def test_invalid_json_reports_line_and_column(tmp_path):
    path = tmp_path / "capsule.json"
    path.write_text('{\n  "env": {\n    "A": {"note": "x",}\n  }\n}\n')
    with pytest.raises(CapsuleFileError, match=r"line 3, column 23"):
        load(path)


@pytest.mark.parametrize(
    "text, message",
    [
        ("[]", "must contain a JSON object"),
        ('{"format": 2}', "uses format 2"),
        ('{"env": []}', '"env" in capsule.json must be an object'),
        ('{"env": {"A": "a note"}}', '"env.A" in capsule.json must be an object'),
    ],
)
def test_wrong_shape_is_refused(tmp_path, text, message):
    path = tmp_path / "capsule.json"
    path.write_text(text)
    with pytest.raises(CapsuleFileError, match=message):
        load(path)


# --- find_project_root ---


def test_root_is_nearest_folder_with_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "src" / "lib").mkdir(parents=True)
    assert find_project_root(tmp_path / "src" / "lib") == tmp_path.resolve()


def test_root_is_nearest_folder_with_capsule_json(tmp_path):
    (tmp_path / "capsule.json").write_text("{}")
    (tmp_path / "src").mkdir()
    assert find_project_root(tmp_path / "src") == tmp_path.resolve()


def test_root_falls_back_to_start(tmp_path):
    start = tmp_path.resolve()
    if any(
        (folder / name).is_file()
        for folder in start.parents
        for name in ("package.json", "capsule.json")
    ):
        pytest.skip("a folder above the temp directory has package.json or capsule.json")
    assert find_project_root(start) == start
