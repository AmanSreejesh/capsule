from pathlib import Path

from capsule_cli.env_files import read_env_files


def test_reads_names_without_values(tmp_path):
    (tmp_path / ".env").write_text(
        "# local secrets\nAPI_KEY=secret\nexport DATABASE_URL = postgres://x\nINVALID-NAME=x\n"
    )
    result = read_env_files(tmp_path)
    assert result.names == {"API_KEY", "DATABASE_URL"}
    assert result.sources == {"API_KEY": (".env",), "DATABASE_URL": (".env",)}
    assert result.files == (".env",)


def test_combines_default_files_and_deduplicates_sources(tmp_path):
    (tmp_path / ".env").write_text("A=1\nSHARED=one\n")
    (tmp_path / ".env.local").write_text("B=2\nSHARED=two\n")
    result = read_env_files(tmp_path)
    assert result.names == {"A", "B", "SHARED"}
    assert result.sources["SHARED"] == (".env", ".env.local")


def test_explicit_relative_file_is_reported_even_when_missing(tmp_path):
    result = read_env_files(tmp_path, [Path("config/dev.env")])
    assert result.names == set()
    assert result.files == ("config/dev.env",)
