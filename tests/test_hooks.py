import subprocess

from capsule_cli import hooks


def test_install_preserves_existing_hook_and_uninstall_removes_only_capsule(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    directory = hooks.hooks_dir(tmp_path)
    path = directory / "post-merge"
    path.write_text("#!/bin/sh\necho existing\n")

    assert set(hooks.install(tmp_path)) == {"post-merge", "post-checkout"}
    assert hooks.install(tmp_path) == []
    assert "echo existing" in path.read_text()
    assert hooks.START in path.read_text()

    assert set(hooks.uninstall(tmp_path)) == {"post-merge", "post-checkout"}
    assert path.read_text() == "#!/bin/sh\necho existing\n"
    assert not (directory / "post-checkout").exists()
