#!/usr/bin/env python3
"""Merge seed + derived data into the page."""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"


def load(name):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main():
    payload = {
        "seed": load("seed.json"),
        "derived": load("derived.json"),
    }
    snapshot = load("fec_snapshot.json")
    if snapshot:
        payload["fec"] = snapshot

    template = (HERE / "site" / "template.html").read_text(encoding="utf-8")
    if "/*__DATA__*/" not in template:
        raise SystemExit("template marker missing")
    body = template.replace("/*__DATA__*/", json.dumps(payload, separators=(",", ":")))

    # Fragment, for publishing as an artifact (the host wraps it).
    out = HERE / "site" / "index.html"
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB)")

    # Standalone document, for opening straight from disk.
    split = body.index("</style>") + len("</style>")
    head, rest = body[:split], body[split:]
    standalone = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        "<style>:root{padding-top:env(safe-area-inset-top,0px);"
        "padding-bottom:env(safe-area-inset-bottom,0px)}"
        "body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n"
        + head + "\n</head>\n<body>\n" + rest + "\n</body>\n</html>\n"
    )
    out2 = HERE / "AIPAC-Money-Tracker.html"
    out2.write_text(standalone, encoding="utf-8")
    print(f"wrote {out2} ({out2.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
