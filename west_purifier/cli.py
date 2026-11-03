import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from .capture import capture
from .runtime import prepare
from .common import run


def locate(project=None, companion=None):
    from .common import config

    start = Path(
        project or os.environ.get("WEST_PURIFIER_PROJECT", Path.cwd())
    ).resolve()
    external = companion or os.environ.get("WEST_PURIFIER_LOCK")
    root = (
        start
        if external
        else next(
            (
                p
                for p in [start, *start.parents]
                if (p / "west-purifier.lock.json").exists()
            ),
            start,
        )
    )
    lock = Path(external).resolve() if external else root / "west-purifier.lock.json"
    if lock.exists():
        data = json.loads(lock.read_text())
        workspace = root.parents[len(Path(data["manifestPath"]).parts) - 1]
        return root, lock, workspace
    workspace = next(
        (p for p in [start, *start.parents] if (p / ".west/config").is_file()), None
    )
    if workspace is not None:
        settings = config(workspace / ".west/config")
        root = (workspace / settings.get("manifest", "path")).resolve()
        return (
            root,
            Path(external).resolve() if external else root / "west-purifier.lock.json",
            workspace,
        )
    return start, lock, start.parent


def native(name, args, root, companion):
    if not companion.exists():
        print(
            "west-purifier: no lockfile; using ordinary impure " + name,
            file=sys.stderr,
        )
        env = dict(os.environ)
        if env.get("WEST_CONFIG_LOCAL") == env.get("WEST_PURIFIER_CONFIG"):
            env.pop("WEST_CONFIG_LOCAL", None)
        env.pop("WEST_PURIFIER_WORKSPACE", None)
        return subprocess.call(
            [str(Path(os.environ["WEST_PURIFIER_ORIGINAL"]) / "bin" / name), *args],
            env=env,
        )
    command = next((value for value in args if not value.startswith("-")), "")
    if command in ("init", "update"):
        raise ValueError(
            "Projects are provided by the lock; use west-purifier lock --update to change them"
        )
    if (
        command == "config"
        and any(value.startswith("manifest.") for value in args)
        and len(args) > 2
    ):
        raise ValueError("Manifest selection is locked; update the lock")
    env = prepare(root, companion)
    return subprocess.call(
        [str(Path(os.environ["WEST_PURIFIER_TOOL"]) / "bin" / name), *args], env=env
    )


def main_impl():
    args = sys.argv[1:]
    if args and args[0].startswith("--native="):
        root, companion, workspace = locate()
        return native(args[0].split("=", 1)[1], args[1:], root, companion)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["lock", "prefetch", "exec", "bundle", "publish"]
    )
    parser.add_argument("--project", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--tag", default="v0.1.0")
    opts, rest = parser.parse_known_args(args)
    if rest[:1] == ["--"]:
        rest = rest[1:]
    root, companion, workspace = locate(opts.project, opts.lock)
    if opts.action == "lock":
        capture(root, companion, workspace, opts.update)
    elif opts.action == "prefetch":
        prepare(root, companion)
    elif opts.action == "exec":
        if not rest:
            raise ValueError("Pass a command after --")
        return subprocess.call(rest, env=prepare(root, companion))
    else:
        prepare(root, companion)
        expression = (
            "import "
            + json.dumps(
                os.environ["WEST_PURIFIER_SDK"] + "/lib/west-purifier/nix/release.nix"
            )
            + " {root="
            + json.dumps(str(root))
            + ";lockFile="
            + json.dumps(str(companion))
            + ";version="
            + json.dumps(opts.tag)
            + ";}"
        )
        output = Path(
            run(
                [
                    "nix",
                    "build",
                    "--impure",
                    "--no-link",
                    "--print-out-paths",
                    "--expr",
                    expression,
                ]
            ).strip()
        )
        if opts.action == "bundle":
            print(output / "west-project.tar.gz")
        else:
            subprocess.run(
                [
                    os.environ["WEST_PURIFIER_GH"],
                    "release",
                    "upload",
                    opts.tag,
                    str(output / "west-project.tar.gz"),
                    "--clobber",
                ],
                cwd=root,
                check=True,
            )
    return 0


def main():
    try:
        raise SystemExit(main_impl())
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print("west-purifier: " + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
