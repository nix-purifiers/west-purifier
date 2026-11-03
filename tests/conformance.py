import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading

repo = Path(__file__).resolve().parent.parent
sdk = Path(
    subprocess.check_output(
        ["nix", "build", str(repo) + "#", "--no-link", "--print-out-paths"], text=True
    ).strip()
)
expression = (
    "let f=builtins.getFlake "
    + json.dumps(str(repo))
    + ';p=import f.inputs.nixpkgs {};in p.buildEnv {name="native-west-test-tools";paths=[p.cmake p.gnumake p.gcc];}'
)
compiler = subprocess.check_output(
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

with tempfile.TemporaryDirectory(prefix="west proof with spaces ") as temporary:
    temp = Path(temporary)
    workspace = temp / "user-workspace"
    root = workspace / "app"
    shutil.copytree(
        repo / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns("build", "__pycache__"),
    )
    (workspace / ".west").mkdir()
    (workspace / ".west/config").write_text("[manifest]\npath = app\nfile = west.yml\n")
    existing = workspace / "deps/jsmn/local-changes.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("preserve this checkout\n")
    env = dict(
        os.environ,
        XDG_CACHE_HOME=str(temp / "xdg"),
        PATH=compiler + "/bin" + os.pathsep + os.environ["PATH"],
    )

    def call(directory, name, *args, success=True, extra=None):
        result = subprocess.run(
            [sdk / "bin" / name, *args],
            cwd=directory,
            env=dict(env, **(extra or {})),
            text=True,
            capture_output=True,
            timeout=300,
        )
        assert (result.returncode == 0) == success, result
        return result

    companion = root / "west-purifier.lock.json"
    before = companion.read_bytes()
    source = root / "main.c"
    original = source.read_text()
    for value in ("42", "43", "42"):
        source.write_text(original.replace("42", value))
        assert call(root, "west", "build").stdout.strip().endswith(value)
    assert companion.read_bytes() == before
    assert existing.read_text() == "preserve this checkout\n"
    assert call(root, "west", "status").stdout == ""
    assert (
        "25647e692c7906b96ffd2b05ca54c097948e879c"
        in call(root, "west", "manifest", "--freeze").stdout
    )
    call(root, "west", "update", success=False)
    subdir = root / "subdir"
    subdir.mkdir()
    assert "jsmn" in call(subdir, "west", "list").stdout
    profiles = list((temp / "xdg/west-purifier").glob("*/*/environment-profile"))
    assert len(profiles) == 1
    profile = profiles[0]
    profile_data = json.loads(profile.read_text())
    manifest = json.loads((Path(profile_data["output"]) / "manifest.json").read_text())
    project = Path(manifest["projects"][0]["source"])
    assert not (project.stat().st_mode & 0o222)
    nested = (
        "import subprocess;print(subprocess.check_output(['west','list'],cwd="
        + repr(str(project))
        + ",text=True))"
    )
    assert (
        "jsmn"
        in call(root, "west-purifier", "exec", "--", "python", "-c", nested).stdout
    )

    closure = subprocess.check_output(
        ["nix-store", "--query", "--requisites", str(profile.resolve())], text=True
    )
    assert str(sdk) in closure
    details = json.loads(
        call(
            root,
            "west-purifier",
            "exec",
            "--",
            "python",
            "-c",
            "import json,os,sys,west;from west.util import west_topdir;print(json.dumps([sys.prefix,west.__file__,west_topdir(),os.environ['VIRTUAL_ENV']]))",
        ).stdout
    )
    assert details[0] == details[3] and "/nix/store/" in details[1]
    assert Path(details[2]).is_relative_to(temp / "xdg")
    assert (
        "pip " in call(root, "west-purifier", "exec", "--", "pip", "--version").stdout
    )
    venv = Path(details[0])
    site = next((venv / "lib").glob("python*/site-packages"))
    (site / "purifier_fixture.py").write_text("value = 42\n")
    assert (
        call(
            root,
            "west-purifier",
            "exec",
            "--",
            "python",
            "-c",
            "import purifier_fixture;print(purifier_fixture.value)",
        ).stdout.strip()
        == "42"
    )
    commands = root / "commands.py"
    commands_before = commands.read_text()
    commands.write_text("import purifier_fixture\n" + commands_before)
    assert call(root, "west", "build").stdout.strip().endswith("42")
    commands.write_text(commands_before)

    # Root commands retain ordinary networking.
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"42")

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert (
            call(
                root,
                "west-purifier",
                "exec",
                "--",
                "python",
                "-c",
                "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:"
                + str(server.server_port)
                + "/').read().decode())",
            ).stdout.strip()
            == "42"
        )
    finally:
        server.shutdown()
        server.server_close()
    external = temp / "companion.json"
    companion.rename(external)
    external_env = {
        "WEST_PURIFIER_PROJECT": str(root),
        "WEST_PURIFIER_LOCK": str(external),
    }
    assert call(root, "west", "build", extra=external_env).stdout.strip().endswith("42")
    archive = Path(
        call(root, "west-purifier", "bundle", "--lock", str(external)).stdout.strip()
    )
    assert archive.is_file()
    # Extract the actual release and consume it with unmodified native West.
    consumer = temp / "ordinary-workspace"
    app = consumer / "app"
    app.mkdir(parents=True)
    with tarfile.open(archive) as released:
        released.extractall(app, filter="data")
    import sys

    sys.path.insert(0, str(sdk / "lib/west-purifier"))
    from west_purifier.layout import configure

    ordinary = configure(consumer, app, manifest)
    ordinary.update(PATH=env["PATH"])
    for name in ("PYTHONPATH", "PYTHONHOME", "WEST_PURIFIER_WORKSPACE"):
        ordinary.pop(name, None)
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
    result = subprocess.run(
        [original_sdk / "bin/west", "build"],
        cwd=app,
        env=ordinary,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0 and result.stdout.strip().endswith("42"), result
    fake_gh = temp / "fake-gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\nimport pathlib,sys\np=pathlib.Path(sys.argv[4]);pathlib.Path(__file__).with_suffix('.uploaded').write_bytes(p.read_bytes())\n"
    )
    fake_gh.chmod(0o755)
    call(
        root,
        "west-purifier",
        "publish",
        "--lock",
        str(external),
        extra={"WEST_PURIFIER_GH": str(fake_gh)},
    )
    assert fake_gh.with_suffix(".uploaded").read_bytes() == archive.read_bytes()
    (root / "west.yml").write_text((root / "west.yml").read_text() + "\n# stale\n")
    call(root, "west", "list", extra=external_env, success=False)
    fallback = temp / "fallback"
    fallback.mkdir()
    assert "ordinary impure" in call(fallback, "west", "--version").stderr
    fake_sdk = temp / "fake-sdk"
    (fake_sdk / "bin").mkdir(parents=True)
    fake = fake_sdk / "bin/west"
    fake.write_text("#!/bin/sh\nprintf native-out\nprintf native-err >&2\nexit 7\n")
    fake.chmod(0o755)
    direct = dict(
        os.environ,
        PYTHONPATH=str(sdk / "lib/west-purifier"),
        WEST_PURIFIER_ORIGINAL=str(fake_sdk),
    )
    result = subprocess.run(
        ["python3", "-m", "west_purifier.cli", "--native=west"],
        cwd=fallback,
        env=direct,
        text=True,
        capture_output=True,
    )
    assert (
        result.returncode == 7
        and result.stdout == "native-out"
        and result.stderr.endswith("native-err")
    ), result
print(
    "Native West edits, readonly Git, existing checkout preservation, private venv, networking, source consumer, publication and fallback passed"
)
