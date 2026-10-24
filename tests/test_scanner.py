import shutil
import subprocess
from pathlib import Path

import pytest

from capsule_cli import scanner
from capsule_cli.scanner import Location, list_source_files, scan_project, scan_source


def names(code: str, path: str = "app.js") -> list[str]:
    return list(scan_source(code.encode(), path).env_vars)


def dynamic_lines(code: str, path: str = "app.js") -> list[int]:
    return [loc.line for loc in scan_source(code.encode(), path).dynamic]


# --- forms that are recorded ---


@pytest.mark.parametrize(
    "code, expected",
    [
        ("process.env.API_KEY", ["API_KEY"]),
        ('process.env["API_KEY"]', ["API_KEY"]),
        ("process.env['API_KEY']", ["API_KEY"]),
        ("process.env[`API_KEY`]", ["API_KEY"]),
        ("process.env?.API_KEY", ["API_KEY"]),
        ("const { A, B = 3, C: renamed } = process.env", ["A", "B", "C"]),
        ('const { "A": renamed } = process.env', ["A"]),
        ("const {\n  A,\n  B = 'x',\n} = process.env", ["A", "B"]),
        ("import.meta.env.VITE_API_URL", ["VITE_API_URL"]),
        ("const { VITE_A } = import.meta.env", ["VITE_A"]),
        ("const port = Number(process.env.PORT ?? 3000)", ["PORT"]),
    ],
)
def test_recorded_forms(code, expected):
    assert names(code) == expected


@pytest.mark.parametrize(
    "code, path",
    [
        ("const key: string = process.env.API_KEY!;", "app.ts"),
        ("const { API_KEY } = process.env as Env;", "app.mts"),
        ("export const App = () => <div>{process.env.API_KEY}</div>;", "App.tsx"),
        ("export const App = () => <div>{process.env.API_KEY}</div>;", "App.jsx"),
    ],
)
def test_typescript_and_jsx(code, path):
    assert names(code, path) == ["API_KEY"]


def test_locations_have_path_and_line():
    result = scan_source(b"// setup\n\nconst a = process.env.A;\n", "src/app.js")
    assert result.env_vars == {"A": [Location("src/app.js", 3)]}


def test_same_var_read_twice_lists_each_line_once():
    result = scan_source(b"process.env.A || process.env.A;\nprocess.env.A;\n", "app.js")
    assert result.env_vars["A"] == [Location("app.js", 1), Location("app.js", 2)]


# --- reads whose name isn't known until runtime ---


def test_dynamic_access_is_a_warning_not_a_name():
    code = "const name = 'X';\nprocess.env[name];\nprocess.env[`${prefix}_KEY`];\n"
    assert names(code) == []
    assert dynamic_lines(code) == [2, 3]


def test_rest_pattern_records_named_keys_and_warns():
    code = "const { A, ...rest } = process.env;"
    assert names(code) == ["A"]
    assert dynamic_lines(code) == [1]


def test_computed_destructuring_key_is_a_warning():
    code = "const { [key]: value } = process.env;"
    assert names(code) == []
    assert dynamic_lines(code) == [1]


# --- things that are not reads ---


@pytest.mark.parametrize(
    "code",
    [
        "// process.env.A",
        "/* process.env.A */",
        "const s = 'process.env.A';",
        "const s = `process.env.A`;",
        "const env = process.env;",
        "someObject.env.A",
    ],
)
def test_comments_strings_and_other_objects_are_ignored(code):
    assert names(code) == []


@pytest.mark.parametrize(
    "code",
    [
        "process.env.A = 'x';",
        "process.env['A'] = 'x';",
        "process.env.A ??= 'x';",
        "delete process.env.A;",
    ],
)
def test_writes_are_not_reads(code):
    assert names(code) == []


def test_tool_provided_vars_are_ignored():
    code = (
        "process.env.NODE_ENV;\n"
        "import.meta.env.MODE; import.meta.env.BASE_URL;\n"
        "import.meta.env.PROD; import.meta.env.DEV; import.meta.env.SSR;\n"
    )
    assert names(code) == []


def test_vite_built_in_names_count_under_process_env():
    # Vite only sets these on import.meta.env; on process.env they're ordinary project vars.
    assert names("process.env.MODE") == ["MODE"]


def test_file_with_syntax_error_is_still_scanned():
    code = "function broken( {\nconst a = process.env.BEFORE;\n}}}\nconst b = process.env.AFTER;\n"
    assert names(code) == ["AFTER", "BEFORE"]


# --- choosing files ---


def _write(root: Path, rel: str, text: str = "process.env.A;\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _make_project(root: Path) -> None:
    for rel in (
        "src/app.ts",
        "src/App.tsx",
        "server.cjs",
        "tests/app.test.js",
        "node_modules/pkg/index.js",
        "dist/bundle.js",
        "public/vendor.min.js",
        "ignored/secret.js",
        "README.md",
    ):
        _write(root, rel)
    _write(root, ".gitignore", "ignored/\n")


EXPECTED_FILES = ["server.cjs", "src/App.tsx", "src/app.ts", "tests/app.test.js"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_project_skips_gitignored_and_dependency_files(tmp_path):
    _make_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert list_source_files(tmp_path) == EXPECTED_FILES


def test_non_git_folder_skips_dependency_and_build_folders(tmp_path, monkeypatch):
    _make_project(tmp_path)
    monkeypatch.setattr(scanner, "_git_files", lambda root: None)
    # Without git, .gitignore isn't read, so ignored/ is scanned.
    assert list_source_files(tmp_path) == ["ignored/secret.js", *EXPECTED_FILES]


def test_scan_project_combines_files(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "_git_files", lambda root: None)
    _write(tmp_path, "b.js", "\nprocess.env.SHARED;\n")
    _write(tmp_path, "a.ts", "process.env.SHARED; process.env[name];\n")
    _write(tmp_path, "node_modules/x/index.js", "process.env.FROM_DEPENDENCY;\n")

    result = scan_project(tmp_path)

    assert result.env_vars == {"SHARED": [Location("a.ts", 1), Location("b.js", 2)]}
    assert result.dynamic == [Location("a.ts", 1)]


def test_project_configuration_can_exclude_paths_and_names(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "_git_files", lambda root: None)
    _write(tmp_path, "src/app.ts", "process.env.API_KEY; process.env.CI;\n")
    _write(tmp_path, "fixtures/example.ts", "process.env.FAKE_SECRET;\n")

    result = scan_project(
        tmp_path,
        exclude_patterns=("fixtures/**",),
        ignored_env=frozenset({"CI"}),
    )

    assert list(result.env_vars) == ["API_KEY"]
