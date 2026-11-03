from pathlib import Path

p = Path("src/west/util.py")
s = p.read_text()
needle = "    cur_dir = pathlib.Path(start or os.getcwd())"
replacement = (
    "    if os.environ.get('WEST_PURIFIER_WORKSPACE'):\n        return os.environ['WEST_PURIFIER_WORKSPACE']\n"
    + needle
)
assert s.count(needle) == 1
p.write_text(s.replace(needle, replacement))
