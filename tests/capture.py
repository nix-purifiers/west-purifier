import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
sdk = Path(
    subprocess.check_output(
        ["nix", "build", str(repo) + "#", "--no-link", "--print-out-paths"], text=True
    ).strip()
)
with tempfile.TemporaryDirectory(prefix="west native capture ") as temporary:
    workspace = Path(temporary)
    root = workspace / "app"
    shutil.copytree(
        repo / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns("build", "__pycache__"),
    )
    (workspace / ".west").mkdir()
    (workspace / ".west/config").write_text("[manifest]\npath = app\nfile = west.yml\n")
    env = dict(os.environ, XDG_CACHE_HOME=str(workspace / "cache"))
    companion = root / "west-purifier.lock.json"
    expected = json.loads(companion.read_text())
    companion.unlink()
    subprocess.run([sdk / "bin/west-purifier", "lock"], cwd=root, env=env, check=True)
    captured = json.loads(companion.read_text())
    assert captured["entries"] == expected["entries"]
    assert captured["frozen"] == expected["frozen"]
    before = companion.read_bytes()
    subprocess.run([sdk / "bin/west-purifier", "lock"], cwd=root, env=env, check=True)
    assert companion.read_bytes() == before
    # Native directory self-imports: track only manifests actually read and
    # membership of the imported directory, while leaving source editable.
    (root / "manifests").mkdir()
    (root / "manifests/dependencies.yml").write_text(
        (repo / "tests/fixtures/import-manifest.yml").read_text()
    )
    (root / "west.yml").write_text(
        "manifest:\n  self:\n    import: manifests\n    west-commands: west-commands.yml\n"
    )
    subprocess.run(
        [sdk / "bin/west-purifier", "lock", "--update"], cwd=root, env=env, check=True
    )
    imported = json.loads(companion.read_text())
    assert imported["entries"] == expected["entries"]
    assert set(imported["inputs"]) == {"west.yml", "manifests/dependencies.yml"}
    assert imported["directories"] == {"manifests": ["dependencies.yml"]}
    (root / "manifests/new.yml").write_text("manifest: {}\n")
    result = subprocess.run(
        [sdk / "bin/west-purifier", "prefetch"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "directory changed" in result.stderr
    shutil.rmtree(root / "manifests")
    (root / "west.yml").write_text("manifest:\n  projects: []\n")
    subprocess.run(
        [sdk / "bin/west-purifier", "lock", "--update"], cwd=root, env=env, check=True
    )
    assert json.loads(companion.read_text())["entries"] == []
    subprocess.run(
        [sdk / "bin/west-purifier", "prefetch"], cwd=root, env=env, check=True
    )
    # A local Git transport is a test fixture for West's project importer;
    # production capture still requires public HTTPS project URLs.
    expression = (
        "let f=builtins.getFlake "
        + json.dumps(str(repo))
        + ";p=import f.inputs.nixpkgs {};in p.python3.withPackages (ps: [ps.west])"
    )
    original_sdk = Path(
        subprocess.check_output(
            [
                "nix",
                "build",
                "--impure",
                "--expr",
                expression,
                "--no-link",
                "--print-out-paths",
            ],
            text=True,
        ).strip()
    )
    provider = workspace / "provider"
    provider.mkdir()
    (provider / "west.yml").write_text(
        (repo / "tests/fixtures/import-manifest.yml").read_text()
    )
    fixture_env = dict(
        env,
        GIT_AUTHOR_NAME="fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_AUTHOR_DATE="2000-01-01T00:00:00Z",
        GIT_COMMITTER_DATE="2000-01-01T00:00:00Z",
    )
    for args in (
        ["init", "-b", "main"],
        ["add", "west.yml"],
        ["commit", "-m", "Provide native imported manifest"],
    ):
        subprocess.run(
            ["git", *args],
            cwd=provider,
            env=fixture_env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=provider, text=True
    ).strip()
    imported_workspace = workspace / "imported-workspace"
    imported_root = imported_workspace / "app"
    imported_root.mkdir(parents=True)
    (imported_workspace / ".west").mkdir()
    local = imported_workspace / ".west/config"
    local.write_text("[manifest]\npath = app\nfile = west.yml\n")
    (imported_root / "west.yml").write_text(
        json.dumps(
            {
                "manifest": {
                    "projects": [
                        {
                            "name": "manifest-provider",
                            "url": provider.as_uri(),
                            "revision": revision,
                            "path": "deps/manifest-provider",
                            "import": True,
                        }
                    ]
                }
            }
        )
    )
    imported_env = dict(
        env,
        WEST_CONFIG_LOCAL=str(local),
        WEST_CONFIG_GLOBAL="/dev/null",
        WEST_CONFIG_SYSTEM="/dev/null",
    )
    subprocess.run(
        [original_sdk / "bin/west", "update"],
        cwd=imported_root,
        env=imported_env,
        check=True,
    )
    snapshot = json.loads(
        subprocess.check_output(
            [
                original_sdk / "bin/python",
                sdk / "lib/west-purifier/native/snapshot.py",
                imported_workspace,
                imported_root,
                "freeze",
            ],
            env=imported_env,
            text=True,
        )
    )
    assert [p["name"] for p in snapshot["frozen"]["manifest"]["projects"]] == [
        "manifest-provider",
        "jsmn",
    ]
    assert set(snapshot["commits"]) == {"manifest-provider", "jsmn"}
    assert set(snapshot["inputs"]) == {"west.yml"}
print("Native West capture, stable lock, directory imports and empty manifest passed")
