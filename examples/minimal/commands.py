from pathlib import Path
import subprocess
from west.commands import WestCommand


class Build(WestCommand):
    def __init__(self):
        super().__init__("build", "Build the example", "Build the example")

    def do_add_parser(self, subparsers):
        return subparsers.add_parser(self.name, help=self.help)

    def do_run(self, args, unknown):
        app = Path(self.manifest.repo_abspath).resolve()
        subprocess.run(
            [
                "cmake",
                "-S",
                str(app),
                "-B",
                str(app / "build"),
                "-DJSMN_SOURCE=" + self.manifest.get_projects(["jsmn"])[0].abspath,
            ],
            check=True,
        )
        subprocess.run(["cmake", "--build", str(app / "build")], check=True)
        subprocess.run([str(app / "build/answer")], check=True)
