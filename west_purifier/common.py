import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess


def run(args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout


def relative(value, dot=False):
    return (
        isinstance(value, str)
        and bool(value)
        and (dot or value != ".")
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
        and "\n" not in value
        and "\r" not in value
    )


def config(path):
    data = configparser.ConfigParser(interpolation=None)
    data.read(path)
    return data


def native_environment():
    env = dict(os.environ)
    if env.get("WEST_CONFIG_LOCAL") == env.get("WEST_PURIFIER_CONFIG"):
        env.pop("WEST_CONFIG_LOCAL", None)
    env.pop("WEST_PURIFIER_WORKSPACE", None)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def validate_inputs(root, data):
    for name, expected in data["inputs"].items():
        if (
            not relative(name)
            or not (root / name).is_file()
            or hashlib.sha256((root / name).read_bytes()).hexdigest()
            != expected["sha256"]
        ):
            raise ValueError("Manifest selection changed; update the lock")
    for name, expected in data["directories"].items():
        path = root / name
        if (
            not relative(name, dot=True)
            or not path.is_dir()
            or sorted(p.name for p in path.iterdir() if p.suffix in (".yml", ".yaml"))
            != expected
        ):
            raise ValueError("Imported manifest directory changed; update the lock")


def load(root, companion):
    data = json.loads(companion.read_text())
    if data.get("version") != 1 or data.get("purifier") != "west":
        raise ValueError("Unsupported West lock")
    if data["sdk"] != os.environ["WEST_PURIFIER_SDK_VERSION"]:
        raise ValueError("West SDK changed; update the lock")
    workspace = root.parents[len(Path(data["manifestPath"]).parts) - 1]
    local = config(workspace / ".west/config")
    if local.has_section("manifest"):
        actual = dict(local["manifest"])
        if (workspace / actual.pop("path", "")).resolve() != root:
            raise ValueError("Native manifest repository changed; update the lock")
        actual.setdefault("file", "west.yml")
        expected = {k: v for k, v in data["nativeConfig"].items() if k != "path"}
        if actual != expected:
            raise ValueError("Native manifest selection changed; update the lock")
    validate_inputs(root, data)
    return data
