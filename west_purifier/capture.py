import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlsplit

from .common import config, load, native_environment, relative, run, validate_inputs


def capture(root, companion, workspace, update=False):
    if companion.exists() and not update:
        load(root, companion)
        return
    previous = json.loads(companion.read_text()) if companion.exists() else {}
    local = config(workspace / ".west/config")
    if not local.has_section("manifest"):
        if not previous:
            raise ValueError("Initialize a native workspace with west init -l first")
        local["manifest"] = previous["nativeConfig"]
        local["manifest"]["path"] = str(root.relative_to(workspace))
    manifest_path = local.get("manifest", "path")
    manifest_file = local.get("manifest", "file", fallback="west.yml")
    if (
        not relative(manifest_path)
        or not relative(manifest_file)
        or (workspace / manifest_path).resolve() != root
    ):
        raise ValueError("Use a manifest repository within the native workspace")
    sdk = Path(os.environ["WEST_PURIFIER_SDK"])
    tool = Path(os.environ["WEST_PURIFIER_ORIGINAL"])
    env = native_environment()
    with tempfile.TemporaryDirectory(prefix="west-capture-") as temporary:
        state = Path(temporary)
        source = state / manifest_path
        shutil.copytree(
            root,
            source,
            ignore=shutil.ignore_patterns(
                ".git", ".west", "build", "result", "__pycache__", ".venv"
            ),
        )
        (state / ".west").mkdir()
        local["manifest"]["file"] = manifest_file
        with (state / ".west/config").open("w") as stream:
            local.write(stream)
        env["WEST_CONFIG_LOCAL"] = str(state / ".west/config")
        run([tool / "bin/west", "update"], cwd=source, env=env)
        helper = [
            tool / "bin/python",
            sdk / "lib/west-purifier/native/snapshot.py",
            state,
            source,
        ]
        names = json.loads(run([*helper, "projects"], env=env))
        if names:
            run([tool / "bin/west", "update", *names], cwd=source, env=env)
        snapshot = json.loads(run([*helper, "freeze"], env=env))
        entries = []
        for item in snapshot["frozen"]["manifest"].get("projects", []):
            url = urlsplit(item["url"])
            if (
                url.scheme != "https"
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError(
                    "The initial integration supports public HTTPS Git projects"
                )
            path = item.get("path", item["name"])
            if (
                not relative(path)
                or Path(path) == Path(manifest_path)
                or Path(path).is_relative_to(manifest_path)
                or Path(manifest_path).is_relative_to(path)
            ):
                raise ValueError(
                    "Project paths must be separate from the manifest repository"
                )
            prefetched = json.loads(
                run(
                    [
                        os.environ["WEST_PURIFIER_PREFETCH_GIT"],
                        "--url",
                        item["url"],
                        "--rev",
                        item["revision"],
                    ],
                    env=env,
                )
            )
            entries.append(
                {
                    "path": path,
                    "hash": prefetched["hash"],
                    "git": {
                        "url": item["url"],
                        "rev": item["revision"],
                        "submodules": False,
                        "leaveDotGit": True,
                        "commitObject": snapshot["commits"][item["name"]],
                    },
                    "west": {"name": item["name"]},
                }
            )
        data = dict(
            version=1,
            purifier="west",
            sdk=os.environ["WEST_PURIFIER_SDK_VERSION"],
            manifestPath=manifest_path,
            manifestFile=manifest_file,
            nativeConfig=dict(local["manifest"]),
            frozen=snapshot["frozen"],
            entries=entries,
            inputs=snapshot["inputs"],
            directories=snapshot["directories"],
        )
        validate_inputs(root, data)
        companion.parent.mkdir(parents=True, exist_ok=True)
        staged = companion.with_name(companion.name + ".tmp")
        staged.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
        staged.replace(companion)
