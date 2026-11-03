from pathlib import Path
import json
import subprocess

repo = Path(__file__).resolve().parent.parent
system = subprocess.check_output(
    ["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"], text=True
).strip()
base = str(repo) + "#checks." + system + ".environment.projects"
projects = json.loads(
    subprocess.check_output(
        ["nix", "eval", "--json", base, "--apply", "ps: map (p: p.source.drvPath) ps"],
        text=True,
    )
)
subprocess.run(
    ["nix", "build", "--rebuild", "--no-link", *[p + "^*" for p in projects]],
    check=True,
)
print("Native West Git projects rebuilt identically")
