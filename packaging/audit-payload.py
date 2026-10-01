"""Record exact portable payload and recursively inspect every PE import."""
from pathlib import Path
import hashlib
import json
import os
import sys
import pefile

root = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
files = [p for p in root.rglob("*") if p.is_file()]
names = {p.name.lower() for p in files}
system = Path(os.environ["SystemRoot"]) / "System32"
entries = []
missing = []
for path in sorted(files):
    item = {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if path.suffix.lower() in {".exe", ".dll", ".pyd"}:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                              pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        imports = sorted({entry.dll.decode("ascii").lower()
                          for field in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
                          for entry in getattr(pe, field, [])})
        item["imports"] = imports
        item["machine"] = hex(pe.FILE_HEADER.Machine)
        for name in imports:
            if name in names:
                continue
            # VC runtime must be shipped even if the build PC has it installed.
            if name.startswith(("vcruntime", "msvcp", "concrt")):
                missing.append({"importer": item["path"], "missing": name})
            elif name.startswith(("api-ms-win-", "ext-ms-win-")) or (system / name).is_file():
                continue
            else:
                missing.append({"importer": item["path"], "missing": name})
        pe.close()
    entries.append(item)
report = {"root": str(root), "file_count": len(entries), "bytes": sum(x["bytes"] for x in entries),
          "missing_imports": missing, "files": entries}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: report[key] for key in ("file_count", "bytes", "missing_imports")}, indent=2))
raise SystemExit(bool(missing))
