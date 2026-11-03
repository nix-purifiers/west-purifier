import fcntl
import hashlib
import json
import os
import shlex
from pathlib import Path

from .common import load, native_environment, run
from .layout import configure


def prepare(root, companion):
    data = load(root, companion)
    generation = hashlib.sha256(
        companion.read_bytes() + os.environ["WEST_PURIFIER_SDK"].encode()
    ).hexdigest()[:20]
    key = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    state = cache_home / "west-purifier" / key / generation
    state.mkdir(parents=True, exist_ok=True)
    expression = (
        "import "
        + json.dumps(
            os.environ["WEST_PURIFIER_SDK"] + "/lib/west-purifier/nix/realize.nix"
        )
        + " {root="
        + json.dumps(str(root))
        + ";lockFile="
        + json.dumps(str(companion))
        + ";sdk="
        + json.dumps(os.environ["WEST_PURIFIER_SDK"])
        + ";}"
    )
    profile = Path(
        run(
            [
                "nix",
                "build",
                "--impure",
                "--expr",
                expression,
                "--out-link",
                str(state / "environment-profile"),
                "--print-out-paths",
            ]
        ).strip()
    )
    manifest = json.loads(
        (Path(json.loads(profile.read_text())["output"]) / "manifest.json").read_text()
    )
    if manifest["sdk"] != data["sdk"]:
        raise ValueError("Prepared West SDK differs from the lock")
    with (state / "initialization.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        tool = Path(os.environ["WEST_PURIFIER_TOOL"])
        venv = state / "venv"
        if not (venv / "pyvenv.cfg").exists():
            run(
                [
                    tool / "bin/python",
                    "-m",
                    "venv",
                    "--system-site-packages",
                    "--without-pip",
                    str(venv),
                ],
                env=native_environment(),
            )
        for name in ("pip", "pip3"):
            entry = venv / "bin" / name
            if not entry.exists():
                entry.write_text(
                    "#!"
                    + os.environ["WEST_PURIFIER_SHELL"]
                    + "\nexec "
                    + shlex.quote(str(venv / "bin/python"))
                    + ' -m pip "$@"\n'
                )
                entry.chmod(0o755)
        env = configure(state / "workspace", root, manifest)
    site = Path(os.environ["WEST_PURIFIER_TOOL_SITE"])
    env["WEST_PURIFIER_PROJECT"] = str(root)
    env["WEST_PURIFIER_LOCK"] = str(companion)
    env["VIRTUAL_ENV"] = str(venv)
    env["PIP_CACHE_DIR"] = str(state / "pip-cache")
    env["PYTHONPATH"] = str(site) + os.pathsep + str(venv / site.relative_to(tool))
    env.pop("PYTHONHOME", None)
    env["PATH"] = (
        str(Path(os.environ["WEST_PURIFIER_SDK"]) / "bin")
        + os.pathsep
        + str(venv / "bin")
        + os.pathsep
        + env["PATH"]
    )
    return env
