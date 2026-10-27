#!/usr/bin/env python3
"""Package the project for handover: dist/AIPAC-Money-Tracker-handover.zip"""
import hashlib
import pathlib
import zipfile
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "dist" / "AIPAC-Money-Tracker-handover.zip"

INCLUDE = [
    "START-HERE.md", "README.md", "LICENSE", "requirements.txt", ".env.example", ".gitignore",
    "refresh.py", "parse_bulk.py", "make_seed.py", "ingest.py", "build_site.py",
    "test_refresh.py", "AIPAC-Money-Tracker.html",
    "site/template.html", "site/index.html",
    "handover/index.html", "handover/INTEGRATION.md", "handover/data.json",
    "handover/embed-example.html",
    ".github/workflows/refresh.yml",
    "data/seed.json", "data/derived.json", "data/last_refresh.txt",
    "data/pp_aipac_c4.json", "data/pp_aief_c3.json",
]


def main():
    files = []
    for name in INCLUDE:
        p = ROOT / name
        if not p.exists():
            raise SystemExit(f"missing: {name}")
        files.append(p)

    lines = [f"AIPAC Money Tracker handover", f"generated {date.today().isoformat()}",
             f"python {__import__('sys').version.split()[0]}", "", "sha256  bytes  path"]
    for p in sorted(files):
        data = p.read_bytes()
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {len(data):>8}  {p.relative_to(ROOT).as_posix()}")

    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(ROOT).as_posix())
        z.writestr("MANIFEST.txt", "\n".join(lines) + "\n")

    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB, {len(files)+1} files)")


if __name__ == "__main__":
    main()
