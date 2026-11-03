"""Observe native manifest inputs and serialize native resolved/frozen projects."""

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from west.manifest import Manifest

workspace = Path(sys.argv[1]).resolve()
source = Path(sys.argv[2]).resolve()
files = {}
directories = {}
read_text = Path.read_text
iterdir = Path.iterdir


def observe_read(path, *args, **kwargs):
    text = read_text(path, *args, **kwargs)
    real = path.resolve()
    if real.is_relative_to(source):
        files[str(real.relative_to(source))] = {
            "sha256": hashlib.sha256(real.read_bytes()).hexdigest()
        }
    return text


def observe_directory(path):
    children = list(iterdir(path))
    real = path.resolve()
    if real.is_relative_to(source):
        directories[str(real.relative_to(source))] = sorted(
            p.name for p in children if p.suffix in (".yml", ".yaml")
        )
    return iter(children)


Path.read_text = observe_read
Path.iterdir = observe_directory
try:
    manifest = Manifest.from_topdir(workspace)
finally:
    Path.read_text = read_text
    Path.iterdir = iterdir
if sys.argv[3] == "projects":
    print(json.dumps([p.name for p in manifest.projects[1:]]))
else:
    frozen = manifest.as_frozen_dict()
    commits = {}
    for project, item in zip(
        manifest.projects[1:], frozen["manifest"].get("projects", []), strict=True
    ):
        if project.submodules:
            raise ValueError("Submodule selection needs an additional West provider")
        revision = item["revision"]
        commit = subprocess.check_output(
            ["git", "-C", project.abspath, "cat-file", "commit", revision]
        )
        tree = subprocess.check_output(
            ["git", "-C", project.abspath, "ls-tree", "-r", "-z", revision]
        )
        links = []
        for entry in tree.split(b"\0"):
            if entry:
                metadata, path = entry.split(b"\t", 1)
                mode, kind, digest = metadata.split()
                if mode == b"160000":
                    links.append({"path": path.decode(), "rev": digest.decode()})
        commits[project.name] = {
            "object": base64.b64encode(commit).decode(),
            "gitlinks": links,
        }
    print(
        json.dumps(
            {
                "frozen": frozen,
                "commits": commits,
                "inputs": files,
                "directories": directories,
            },
            sort_keys=True,
        )
    )
