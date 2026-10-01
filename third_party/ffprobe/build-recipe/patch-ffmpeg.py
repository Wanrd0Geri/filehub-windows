"""Apply two documented local fixes and retain an exact unified source patch."""
from pathlib import Path
import difflib
import sys

root = Path(sys.argv[1])
patch = []
for name in ("configure", "libavformat/mov.c"):
    path = root / name
    old = path.read_text(encoding="utf-8")
    if name == "configure":
        new = old.replace("grep -q ^Microsoft", "grep -q Microsoft").replace(
            "grep ^Microsoft | head", "grep Microsoft | head")
    else:
        new = old.replace("    ff_mov_read_chnl(c->fc, pb, st);",
                          "    ret = ff_mov_read_chnl(c->fc, pb, st);")
    if old == new:
        raise SystemExit(f"Expected pristine source patch context: {name}")
    path.write_text(new, encoding="utf-8", newline="\n")
    patch.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                    fromfile="a/" + name, tofile="b/" + name))
target = Path(__file__).resolve().parents[1] / "third_party/ffprobe/filehub.patch"
target.write_text("".join(patch), encoding="utf-8", newline="\n")
