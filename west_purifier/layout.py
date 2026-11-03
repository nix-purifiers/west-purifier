"""Native West workspace layout, shared by installed commands and Nix builds."""

import configparser
import json
import os
from pathlib import Path
import subprocess
import sys


def configure(workspace, source, manifest):
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".west").mkdir(exist_ok=True)
    aliases = [(manifest["manifestPath"], str(source))] + [
        (p["path"], p["source"]) for p in manifest["projects"]
    ]
    for name, target in aliases:
        alias = workspace / name
        alias.parent.mkdir(parents=True, exist_ok=True)
        if alias.exists() or alias.is_symlink():
            if alias.resolve() != Path(target).resolve():
                raise ValueError(
                    "Private West project differs from the locked environment"
                )
        else:
            alias.symlink_to(target, target_is_directory=True)
    local = workspace / ".west/config"
    settings = configparser.ConfigParser(interpolation=None)
    if local.exists():
        settings.read(local)
    else:
        settings["manifest"] = manifest["nativeConfig"]
        settings["manifest"]["path"] = manifest["manifestPath"]
        settings["manifest"]["file"] = manifest["frozen"]
        with local.open("w") as stream:
            settings.write(stream)
    if (
        settings.get("manifest", "path") != manifest["manifestPath"]
        or settings.get("manifest", "file") != manifest["frozen"]
    ):
        raise ValueError("Private West manifest configuration changed")
    env = dict(
        os.environ,
        WEST_PURIFIER_WORKSPACE=str(workspace),
        WEST_CONFIG_LOCAL=str(local),
        GIT_OPTIONAL_LOCKS="0",
    )
    env["WEST_PURIFIER_CONFIG"] = str(local)
    count = int(env.get("GIT_CONFIG_COUNT", "0"))
    for project in manifest["projects"]:
        env["GIT_CONFIG_KEY_" + str(count)] = "safe.directory"
        env["GIT_CONFIG_VALUE_" + str(count)] = project["source"]
        count += 1
    env["GIT_CONFIG_COUNT"] = str(count)
    return env


if __name__ == "__main__":
    manifest = json.loads(Path(sys.argv[3]).read_text())
    env = configure(Path(sys.argv[1]), Path(sys.argv[2]), manifest)
    raise SystemExit(subprocess.call(sys.argv[4:], env=env))
