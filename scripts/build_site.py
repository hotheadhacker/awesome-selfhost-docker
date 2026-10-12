#!/usr/bin/env python3
"""Generate the static website (index.html, sitemap.xml, robots.txt) from README.md.

README.md is the single source of truth. Run after editing it:

    python3 scripts/build_site.py

No dependencies beyond the Python standard library. Repo stats are fetched from the
GitHub API when reachable and fall back to the previous values otherwise.
"""

import datetime as dt
import html
import json
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "hotheadhacker/awesome-selfhost-docker"
SITE_URL = "https://awesome-selfhost-docker.vercel.app/"
REPO_URL = f"https://github.com/{REPO}"
SPONSOR_URL = "https://github.com/sponsors/hotheadhacker"
SPONSOR_INQUIRY_URL = f"{REPO_URL}/issues/new?title=Sponsorship%20inquiry&labels=sponsorship"
SUBMIT_URL = f"{REPO_URL}/edit/main/README.md"
GITADS_IMG = f"https://gitads.dev/v1/ad-serve?source={REPO}@github"
GITADS_LINK = f"https://gitads.dev/v1/ad-track?source={REPO}@github"
NEW_WINDOW_DAYS = 365
FALLBACK_STATS = {"stars": 4089, "forks": 211}

CATEGORIES = {
    "Productivity": ("📝", "Notes, documents, wikis, kanban boards and office suites you can run on your own server."),
    "Development": ("🛠️", "Git hosting, CI/CD, IDEs, databases and developer tooling, ready to deploy with Docker."),
    "Media": ("🎬", "Media servers, music streaming, photo libraries, downloaders and the *arr stack."),
    "Communication": ("💬", "Chat, video calls, email servers and federated social networks."),
    "Security": ("🔐", "Password managers, identity and access, VPNs, firewalls and intrusion detection."),
    "Monitoring": ("📈", "Metrics, uptime, logs and observability for your infrastructure."),
    "File Sharing": ("📁", "File sync, cloud storage, object storage and NAS software."),
    "Home Automation": ("🏠", "Smart-home hubs and IoT automation platforms."),
    "Analytics": ("📊", "Privacy-friendly web analytics and business intelligence."),
    "Miscellaneous": ("🧩", "Ad blocking, RSS, bookmarks, recipes, finance and other handy self-hosted apps."),
}

ROW_RE = re.compile(r"^\|\s*\[\s*(?P<name>[^\]]+?)\s*\]\((?P<url>[^)]+)\)\s*\|\s*(?P<desc>.*?)\s*\|\s*$")


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def readme_before(days):
    """README.md as it was `days` ago, or None when the history is unavailable."""
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    try:
        rev = subprocess.run(["git", "rev-list", "-1", f"--before={since}", "HEAD"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        if not rev:
            return None
        return subprocess.run(["git", "show", f"{rev}:README.md"],
                              cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def parse_readme():
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    previous = readme_before(NEW_WINDOW_DAYS)
    sections, current = [], None
    for line in lines:
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1)
            current = {"title": title, "items": []} if title in CATEGORIES else None
            if current:
                sections.append(current)
            continue
        row = ROW_RE.match(line)
        if current is not None and row:
            url = row.group("url").strip()
            repo = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", url)
            current["items"].append({
                "name": row.group("name").strip(),
                "url": url,
                "desc": row.group("desc").strip().rstrip("|").strip(),
                "owner": repo.group(1) if repo else "",
                "path": f"{repo.group(1)}/{repo.group(2)}" if repo else re.sub(r"^https?://", "", url),
                "new": previous is not None and f"({url})" not in previous,
            })
    return [s for s in sections if s["items"]]


def fetch_stats():
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}", headers={"User-Agent": "build-site"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        return {"stars": data["stargazers_count"], "forks": data["forks_count"]}
    except Exception:
        return FALLBACK_STATS


def compact(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def esc(text):
    return html.escape(text, quote=True)


def render_card(item, category):
    owner = esc(item["owner"])
    avatar = (
        f'<img class="avatar" src="https://github.com/{owner}.png?size=80" alt="" width="40" height="40" loading="lazy" decoding="async">'
        if owner else '<span class="avatar" aria-hidden="true"></span>'
    )
    badge = '<span class="badge">New</span>' if item["new"] else ""
    search = esc(f'{item["name"]} {item["desc"]} {item["path"]} {category}'.lower())
    return f"""<li class="card" data-search="{search}"{' data-new' if item["new"] else ''}>
<a class="card-link" href="{esc(item["url"])}" target="_blank" rel="noopener">
{avatar}<div class="card-body"><div class="card-title"><h3>{esc(item["name"])}</h3>{badge}</div>
<div class="card-path">{esc(item["path"])}</div>
<p>{esc(item["desc"])}</p></div></a></li>"""


def render(sections, stats):
    total = sum(len(s["items"]) for s in sections)
    new_total = sum(i["new"] for s in sections for i in s["items"])
    today = dt.date.today().isoformat()

    chips = [f'<button class="chip" type="button" data-cat="all" aria-pressed="true">All <span>{total}</span></button>']
    if new_total:
        chips.append(f'<button class="chip" type="button" data-cat="new" aria-pressed="false">✨ New <span>{new_total}</span></button>')
    body = []
    for s in sections:
        sid = slugify(s["title"])
        icon, blurb = CATEGORIES[s["title"]]
        chips.append(
            f'<button class="chip" type="button" data-cat="{sid}" aria-pressed="false">{icon} {esc(s["title"])} <span>{len(s["items"])}</span></button>'
        )
        cards = "\n".join(render_card(i, s["title"]) for i in s["items"])
        body.append(f"""<section class="category" id="{sid}" aria-labelledby="{sid}-h">
<header class="category-head"><h2 id="{sid}-h"><span class="cat-icon" aria-hidden="true">{icon}</span>{esc(s["title"])} <small>{len(s["items"])}</small></h2>
<p>{esc(blurb)}</p></header>
<ul class="grid">
{cards}
</ul></section>""")

    faq = [
        ("What is Awesome Self-Host Docker?",
         f"A community-curated list of {total} open-source applications you can self-host with Docker and docker-compose, organised into {len(sections)} categories."),
        ("Do all of these projects run in Docker?",
         "Yes. Every project is open source and provides an official or well-maintained Docker image or docker-compose setup."),
        ("How do I add a project?",
         "Open a pull request on GitHub that adds one row to the matching table in README.md. Projects must be open source, Docker-deployable, maintained and have some community adoption."),
        ("How can I sponsor the list?",
         "Sponsor the maintainer on GitHub Sponsors, or open a sponsorship inquiry on GitHub to place your project in front of thousands of self-hosters."),
    ]
    faq_html = "\n".join(f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in faq)

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": SITE_URL + "#website", "url": SITE_URL, "name": "Awesome Self-Host Docker",
             "potentialAction": {"@type": "SearchAction", "target": SITE_URL + "?q={search_term_string}",
                                 "query-input": "required name=search_term_string"}},
            {"@type": "CollectionPage", "url": SITE_URL, "name": "Awesome Self-Host Docker",
             "dateModified": today, "isPartOf": {"@id": SITE_URL + "#website"},
             "mainEntity": {"@type": "ItemList", "numberOfItems": total, "itemListElement": [
                 {"@type": "ListItem", "position": n, "name": i["name"], "url": i["url"]}
                 for n, i in enumerate((i for s in sections for i in s["items"]), start=1)]}},
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        ],
    }

    description = (f"Discover {total}+ open-source, self-hosted apps you can deploy with Docker and docker-compose: "
                   "media servers, password managers, monitoring, dev tools, home automation and more.")
    replacements = {
        "%%DESCRIPTION%%": esc(description),
        "%%SITE_URL%%": SITE_URL,
        "%%REPO_URL%%": REPO_URL,
        "%%REPO%%": REPO,
        "%%SPONSOR_URL%%": SPONSOR_URL,
        "%%SPONSOR_INQUIRY_URL%%": SPONSOR_INQUIRY_URL,
        "%%SUBMIT_URL%%": SUBMIT_URL,
        "%%GITADS_IMG%%": esc(GITADS_IMG),
        "%%GITADS_LINK%%": esc(GITADS_LINK),
        "%%TOTAL%%": str(total),
        "%%CATEGORY_COUNT%%": str(len(sections)),
        "%%STARS%%": compact(stats["stars"]),
        "%%FORKS%%": compact(stats["forks"]),
        "%%CHIPS%%": "\n".join(chips),
        "%%SECTIONS%%": "\n".join(body),
        "%%FAQ%%": faq_html,
        "%%JSONLD%%": json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"),
        "%%YEAR%%": str(dt.date.today().year),
        "%%TODAY%%": today,
    }
    page = (ROOT / "scripts" / "template.html").read_text(encoding="utf-8")
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page, total


def main():
    sections = parse_readme()
    stats = fetch_stats()
    page, total = render(sections, stats)
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8")
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE_URL}</loc><lastmod>{dt.date.today().isoformat()}</lastmod>"
        "<changefreq>weekly</changefreq><priority>1.0</priority></url>\n</urlset>\n",
        encoding="utf-8",
    )
    print(f"Built index.html: {total} projects in {len(sections)} categories, {stats['stars']} stars")


if __name__ == "__main__":
    main()
