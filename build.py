#!/usr/bin/env python3
"""
arshitsharma.in build

Rewrites only the text between marker comments. Everything outside a marker
pair is copied through byte for byte, so this cannot touch your prose.

    python3 build.py            build, but only if nothing is broken
    python3 build.py --check    say what would change, write nothing
    python3 build.py --init     one time: add markers and metadata to pages

Markers
    <!--#head-->      ... <!--#/head-->      shared <head> lines
    <!--#header-->    ... <!--#/header-->    masthead and nav
    <!--#footer-->    ... <!--#/footer-->    footer
    <!--#cards:KIND:N--> ... <!--#/cards-->  generated card list
                                             KIND is review|note, N is a
                                             number or the word all

Per page metadata, in the <head> of anything in reviews/ or notes/
    <meta name="x-kind"   content="review">
    <meta name="x-date"   content="2026-08-26">     sorts newest first
    <meta name="x-title"  content="Chili's, HLP Galleria">
    <meta name="x-kicker" content="Nothing went wrong.">
    <meta name="x-meta"   content="2 in 3 &middot; 22 / 30">
    <meta name="x-thumb"  content="images/chilis/quesadillas.jpg">   optional
    <meta name="x-draft"  content="true">                            optional
"""

import re
import sys
import html
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PARTIALS = ROOT / "_partials"
CONTENT_DIRS = ("reviews", "notes")
SKIP = {"404.html"}

errors = []
notes_ = []


def err(where, message):
    errors.append(f"{where}: {message}")


# ---------------------------------------------------------------- pages

def pages():
    """Every html file we manage, root level and one level down."""
    for p in sorted(ROOT.glob("*.html")):
        yield p
    for d in CONTENT_DIRS:
        for p in sorted((ROOT / d).glob("*.html")):
            yield p


def rel(p):
    return p.relative_to(ROOT).as_posix()


# ---------------------------------------------------------------- markers

def block(text, name):
    """Return (start, end) offsets of the inside of a marker pair, or None."""
    open_re = re.compile(r"<!--#" + name + r"(?::[^>]*)?-->")
    close = f"<!--#/{name.split(':')[0]}-->"
    m = open_re.search(text)
    if not m:
        return None
    end = text.find(close, m.end())
    if end == -1:
        return None
    return m, m.end(), end


def replace_block(text, name, new_inner):
    found = block(text, name)
    if not found:
        return text, False
    _, a, b = found
    if text[a:b] == new_inner:
        return text, False
    return text[:a] + new_inner + text[b:], True


# ---------------------------------------------------------------- metadata

REQUIRED = ("x-kind", "x-date", "x-title", "x-kicker", "x-meta")
# metadata is plain text only. HTML in an attribute breaks the parser and
# silently truncates a card, which is exactly the bug this rule prevents.
BANNED = ('"', "<", ">")


def read_meta(text):
    out = {}
    for m in re.finditer(r'<meta\s+name="(x-[a-z]+)"\s+content="(.*?)"\s*/?>', text):
        out[m.group(1)] = m.group(2)
    return out


def collect_content():
    """Read every review and note, validate its metadata, return sorted items."""
    items = []
    for d in CONTENT_DIRS:
        for p in sorted((ROOT / d).glob("*.html")):
            text = p.read_text(encoding="utf-8")
            meta = read_meta(text)
            missing = [k for k in REQUIRED if k not in meta]
            if missing:
                err(rel(p), "missing metadata " + ", ".join(missing))
                continue
            for k, v in meta.items():
                if any(ch in v for ch in BANNED):
                    err(rel(p), f'{k} must be plain text, no quotes or tags: "{v}"')
            if meta["x-kind"] not in ("review", "note"):
                err(rel(p), f'x-kind must be review or note, got "{meta["x-kind"]}"')
                continue
            try:
                d_ = date.fromisoformat(meta["x-date"])
            except ValueError:
                err(rel(p), f'x-date must be YYYY-MM-DD, got "{meta["x-date"]}"')
                continue
            if meta.get("x-thumb"):
                if not (ROOT / meta["x-thumb"]).exists():
                    err(rel(p), f'x-thumb not on disk: {meta["x-thumb"]}')
            items.append({
                "path": rel(p),
                "url": "/" + rel(p),
                "kind": meta["x-kind"],
                "date": d_,
                "title": meta["x-title"],
                "kicker": meta["x-kicker"],
                "meta": meta["x-meta"],
                "score": meta.get("x-score", ""),
                "thumb": meta.get("x-thumb", ""),
                "draft": meta.get("x-draft", "").lower() == "true",
            })
    items.sort(key=lambda i: (i["date"], i["title"]), reverse=True)
    return items


# ---------------------------------------------------------------- cards

def card(item):
    """One card. With a thumb it gets an image, without it stretches full width."""
    if item["thumb"]:
        onerr = ("this.outerHTML='&lt;div class=\\'ph\\'&gt;'"
                 "+this.dataset.slot+'&lt;/div&gt;'")
        img = (
            f'    <img src="{item["thumb"]}" data-slot="{item["thumb"]}"'
            f' alt="{html.escape(item["title"], quote=True)}"\n'
            f'         onerror="{onerr}">\n'
        )
        cls = "post"
    else:
        img = ""
        cls = "post noimg"
    if item["score"]:
        metaline = (f'<span class="score">{item["score"]}</span>'
                    f' &middot; {item["meta"]}')
    else:
        metaline = item["meta"]

    return (
        f'  <a class="{cls}" href="{item["url"]}">\n'
        f'{img}'
        f'    <div>\n'
        f'      <h2>{item["title"]}</h2>\n'
        f'      <p class="kicker">{item["kicker"]}</p>\n'
        f'      <p class="meta">{metaline}</p>\n'
        f'    </div>\n'
        f'  </a>\n'
    )


def cards_for(spec, items):
    kind, count = spec.split(":")
    chosen = [i for i in items if i["kind"] == kind and not i["draft"]]
    if count != "all":
        chosen = chosen[: int(count)]
    if not chosen:
        return "\n  <!-- nothing published yet -->\n"
    return "\n" + "\n".join(card(i) for i in chosen)


# ---------------------------------------------------------------- checker

def check_links(path, text):
    """Every internal href and img src must resolve, case sensitive."""
    depth = len(path.relative_to(ROOT).parts) - 1
    here = path.parent

    for m in re.finditer(r'(?:href|src)="([^"#][^"]*)"', text):
        target = m.group(1)
        if target.startswith(("http://", "https://", "mailto:", "data:", "//")):
            continue
        if target.startswith("/"):
            resolved = ROOT / target.lstrip("/")
        else:
            resolved = (here / target).resolve()
        if not resolved.exists():
            err(rel(path), f"dead path: {target}")
        else:
            # exists() is case insensitive on some systems, so compare properly
            try:
                real = resolved.resolve()
                if real.name not in [c.name for c in real.parent.iterdir()]:
                    err(rel(path), f"wrong case: {target}")
            except OSError:
                pass
    _ = depth


# ---------------------------------------------------------------- build

def build(write=True):
    for name in ("head.html", "header.html", "footer.html"):
        if not (PARTIALS / name).exists():
            err("_partials", f"missing {name}")
    if errors:
        return []

    head_t = (PARTIALS / "head.html").read_text(encoding="utf-8").strip("\n")
    header_t = (PARTIALS / "header.html").read_text(encoding="utf-8").strip("\n")
    footer_t = (PARTIALS / "footer.html").read_text(encoding="utf-8").strip("\n")

    items = collect_content()
    if errors:
        return []

    planned = []
    for p in pages():
        if p.name in SKIP and False:
            continue
        text = original = p.read_text(encoding="utf-8")
        depth = len(p.relative_to(ROOT).parts) - 1
        root_prefix = "../" * depth

        # which nav item is the current page
        if depth == 0:
            current = p.stem
        else:
            current = {"reviews": "eating", "notes": "notes"}[p.parent.name]

        head = head_t.replace("{{ROOT}}", root_prefix)
        header = header_t
        for key in ("index", "photographs", "notes", "eating", "about"):
            header = header.replace(
                "{{CUR:" + key + "}}",
                ' aria-current="page"' if key == current else "",
            )

        for name, body in (("head", head), ("header", header), ("footer", footer_t)):
            if block(text, name) is None:
                err(rel(p), f"no <!--#{name}--> markers, run --init")
                continue
            text, _ = replace_block(text, name, "\n" + body + "\n")

        for m in re.finditer(r"<!--#cards:([a-z]+:[a-z0-9]+)-->", text):
            text, _ = replace_block(text, "cards:" + m.group(1),
                                    cards_for(m.group(1), items))

        check_links(p, text)
        if text != original:
            planned.append((p, text))

    if errors:
        return []

    if write:
        for p, text in planned:
            p.write_text(text, encoding="utf-8")
    return planned


# ---------------------------------------------------------------- init

def init():
    """One time. Wrap the existing header, footer and head lines in markers."""
    touched = []
    for p in pages():
        text = original = p.read_text(encoding="utf-8")

        if "<!--#head-->" not in text:
            m = re.search(
                r'<meta charset.*?<link rel="stylesheet" href="[^"]+">',
                text, re.S)
            if m:
                text = text[:m.start()] + "<!--#head-->\n" + m.group(0) + \
                       "\n<!--#/head-->" + text[m.end():]
            else:
                err(rel(p), "could not find the head block to wrap")

        if "<!--#header-->" not in text:
            m = re.search(r'<header class="masthead">.*?</header>', text, re.S)
            if m:
                text = text[:m.start()] + "<!--#header-->\n" + m.group(0) + \
                       "\n<!--#/header-->" + text[m.end():]
            else:
                err(rel(p), "could not find the masthead to wrap")

        if "<!--#footer-->" not in text:
            m = re.search(r'<footer class="wrap">.*?</footer>', text, re.S)
            if m:
                text = text[:m.start()] + "<!--#footer-->\n" + m.group(0) + \
                       "\n<!--#/footer-->" + text[m.end():]
            else:
                err(rel(p), "could not find the footer to wrap")

        if text != original:
            p.write_text(text, encoding="utf-8")
            touched.append(rel(p))
    return touched


# ---------------------------------------------------------------- main

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "--init":
        touched = init()
        for t in touched:
            print("  markers added:", t)
        if errors:
            print("\nPROBLEMS")
            for e in errors:
                print("  ", e)
            return 1
        print(f"\n{len(touched)} files given markers. Now add the x- metadata "
              "to everything in reviews/ and notes/, then run the build.")
        return 0

    planned = build(write=(mode != "--check"))

    if errors:
        print("BUILD FAILED, nothing was written\n")
        for e in errors:
            print("  ", e)
        return 1

    if mode == "--check":
        if planned:
            print("These files are out of date:")
            for p, _ in planned:
                print("  ", rel(p))
            return 1
        print("Everything is up to date.")
        return 0

    if not planned:
        print("Nothing to do, everything already current.")
    else:
        for p, _ in planned:
            print("  rebuilt:", rel(p))
        print(f"\n{len(planned)} files rebuilt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
