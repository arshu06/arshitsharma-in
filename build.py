#!/usr/bin/env python3
"""
arshitsharma.in build

Rewrites only the text between marker comments. Everything outside a marker
pair is copied through byte for byte, so this cannot touch your prose.

    python3 build.py            build, but only if nothing is broken
    python3 build.py --check    say what would change, write nothing

New pages are made by copying an existing one. The <title> and the
<meta name="description"> go ABOVE <!--#head-->, never between the markers,
because everything between them is replaced by _partials/head.html on
every build.

Markers
    <!--#head-->      ... <!--#/head-->      shared <head> lines
    <!--#header-->    ... <!--#/header-->    masthead and nav
    <!--#footer-->    ... <!--#/footer-->    footer
    <!--#nav-->       ... <!--#/nav-->       previous / next, added for you
    <!--#reply-->     ... <!--#/reply-->     reply form, added for you
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

SITE = "https://arshitsharma.in"
FORM_KEY = "127a2d84-9ea3-45c1-983c-66b519895517"   # web3forms, public by design

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


def nav_for(item, items):
    """The older and newer entry of the same kind. Items are newest first."""
    same = [i for i in items if i["kind"] == item["kind"] and not i["draft"]]
    idx = next((n for n, i in enumerate(same) if i["path"] == item["path"]), None)
    if idx is None:
        return "\n"
    newer = same[idx - 1] if idx > 0 else None
    older = same[idx + 1] if idx + 1 < len(same) else None
    if not newer and not older:
        return "\n"
    out = ['\n  <nav class="pagenav">\n']
    if older:
        out.append(f'    <a class="prev" href="{older["url"]}">'
                   f'<span>Previous</span>{older["title"]}</a>\n')
    if newer:
        out.append(f'    <a class="next" href="{newer["url"]}">'
                   f'<span>Next</span>{newer["title"]}</a>\n')
    out.append('  </nav>\n')
    return "".join(out)


# ---------------------------------------------------------------- feed

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def rfc822(d):
    """RSS wants this exact shape, and strftime is locale dependent."""
    return (f"{DAYS[d.weekday()]}, {d.day:02d} {MONTHS[d.month - 1]} "
            f"{d.year} 09:00:00 +0530")


def xml_escape(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def write_feed(items, write=True):
    """feed.xml, from the same metadata the cards use. Drafts stay out."""
    live = [i for i in items if not i["draft"]][:30]
    rows = []
    for i in live:
        rows.append(
            "  <item>\n"
            f"    <title>{xml_escape(i['title'])}</title>\n"
            f"    <link>{SITE}{i['url']}</link>\n"
            f"    <guid isPermaLink=\"true\">{SITE}{i['url']}</guid>\n"
            f"    <pubDate>{rfc822(i['date'])}</pubDate>\n"
            f"    <description>{xml_escape(i['kicker'])}</description>\n"
            "  </item>"
        )
    built = rfc822(live[0]["date"]) if live else rfc822(date.today())
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "<channel>\n"
        "  <title>Arshit Sharma</title>\n"
        f"  <link>{SITE}/</link>\n"
        "  <description>Weekly notes, photographs, restaurant reviews, "
        "and whatever else I feel like.</description>\n"
        "  <language>en</language>\n"
        f'  <atom:link href="{SITE}/feed.xml" rel="self" '
        'type="application/rss+xml"/>\n'
        f"  <lastBuildDate>{built}</lastBuildDate>\n"
        + "\n".join(rows) + "\n"
        "</channel>\n"
        "</rss>\n"
    )
    target = ROOT / "feed.xml"
    changed = (not target.exists()) or target.read_text(encoding="utf-8") != feed
    if changed and write:
        target.write_text(feed, encoding="utf-8")
    return changed


# ---------------------------------------------------------------- reply form

def reply_form(item):
    """One form per page. The hidden subject tells you which page it came
    from, so a reply to Wk 34 does not arrive looking like every other one."""
    subject = f"Reply: {item['title']}"
    return f'''
  <section class="reply">
    <h2>Reply</h2>
    <p class="note">If you want to say something about this one, correct me, or
    tell me I have got something wrong, this goes straight to my inbox. Nothing is
    published here automatically. If it turns into a correction it goes in the
    Edits section with your name on it, or without, whichever you prefer.</p>
    <form action="https://api.web3forms.com/submit" method="POST">
      <input type="hidden" name="access_key" value="{FORM_KEY}">
      <input type="hidden" name="subject" value="{subject}">
      <input type="hidden" name="from_name" value="arshitsharma.in">
      <input type="hidden" name="page" value="{SITE}{item["url"]}">
      <input type="hidden" name="redirect" value="{SITE}/thanks.html">
      <input type="checkbox" name="botcheck" class="hp" tabindex="-1" autocomplete="off">

      <label for="r-message">What you want to say</label>
      <textarea id="r-message" name="message" required></textarea>

      <label for="r-name">Your name</label>
      <input id="r-name" type="text" name="name" required autocomplete="name">

      <label for="r-email">Email, so I can reply</label>
      <input id="r-email" type="email" name="email" required autocomplete="email">

      <button type="submit">Send it</button>
    </form>
  </section>
'''


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

    # Keep going even if metadata is broken. We are not writing anything while
    # errors exist, so it is safe to carry on and collect every problem in one
    # pass rather than making you fix them one push at a time.
    items = collect_content()

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
                err(rel(p), f"no <!--#{name}--> markers, copy them from another page")
                continue
            text, _ = replace_block(text, name, "\n" + body + "\n")

        # previous / next. if the page has no markers yet we add an empty
        # pair before </main>. that insertion only ever adds, so unlike the old
        # --init it cannot swallow anything that was already on the page.
        mine = next((i for i in items if i["path"] == rel(p)), None)
        if mine:
            if "<!--#nav-->" not in text:
                if "</main>" in text:
                    text = text.replace(
                        "</main>", "<!--#nav-->\n<!--#/nav-->\n\n</main>", 1)
                else:
                    err(rel(p), "no </main>, cannot place the nav markers")
            if "<!--#reply-->" not in text:
                where = "<!--#nav-->" if "<!--#nav-->" in text else "</main>"
                text = text.replace(
                    where, "<!--#reply-->\n<!--#/reply-->\n\n" + where, 1)
            text, _ = replace_block(text, "reply", reply_form(mine))
            text, _ = replace_block(text, "nav", nav_for(mine, items))

        for m in re.finditer(r"<!--#cards:([a-z]+:[a-z0-9]+)-->", text):
            text, _ = replace_block(text, "cards:" + m.group(1),
                                    cards_for(m.group(1), items))

        check_links(p, text)
        if text != original:
            planned.append((p, text))

    if errors:
        return []

    if write_feed(items, write) and not any(x[0].name == "feed.xml" for x in planned):
        planned.append((ROOT / "feed.xml", None))

    if write:
        for p, text in planned:
            if text is not None:
                p.write_text(text, encoding="utf-8")
    return planned


# ---------------------------------------------------------------- main

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "--init":
        print("--init has been removed. It wrapped the shared <head> lines in\n"
              "markers by pattern, and the pattern was wrong: it swallowed the\n"
              "<title> and <meta name=description> of twelve pages, which the\n"
              "next build then overwrote with the shared partial.\n\n"
              "To add markers to a new page, copy an existing one. The <title>\n"
              "and description belong ABOVE <!--#head-->, never inside it.")
        return 1

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
