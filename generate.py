#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 missing-foss
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Builds the missing-foss.github.io landing page. Renders template.html.j2
against live GitHub API data (org repo list, each repo's latest release) plus
data/repos.yaml's small curated overlay. Nothing
about repo names, versions, or release state may be hardcoded, or the page
just rots the way profile/README.md already did (still listing three
repos, missing two).

    python3 generate.py [output_dir]      # default: _site/

GITHUB_TOKEN (optional, but always set in CI): raises the API's rate limit
from 60/hour to 5000/hour. Every request here is read-only against public
data, so an unauthenticated run (e.g. testing locally with no token) still
works, just at the lower ceiling.
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ORG = "missing-foss"
THIS_REPO = "missing-foss.github.io"
API_ROOT = "https://api.github.com"
ROOT = Path(__file__).resolve().parent


def _api_get(path: str) -> dict | list | None:
    """GET against the GitHub API. Returns None for a 404 (meaning "doesn't
    exist" -- used for "no release yet", not an error), raises for anything
    else 4xx/5xx, since a real failure here means a stale/broken page ships
    instead of the run just failing loudly."""
    req = urllib.request.Request(f"{API_ROOT}{path}", headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            import json
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _list_org_repos() -> list[dict]:
    """Every public, non-archived, non-fork repo in the org, paginated (the
    API caps a single page at 100) -- so a sixth application appears here
    without this script changing, only data/repos.yaml gaining an entry for
    its role/platform text."""
    repos = []
    page = 1
    while True:
        batch = _api_get(f"/orgs/{ORG}/repos?type=public&per_page=100&page={page}")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return [r for r in repos if not r["archived"] and not r["fork"]]


def _latest_release_tag(repo_name: str) -> str | None:
    """Every repo tags releases as a bare 'vX.Y.Z', so there is one rule to
    strip and no per-repo prefix to carry in the overlay. This used to take a
    prefix per entry, back when each client prefixed its own short name
    ('android-vX.Y.Z'); if a repo ever diverges again, the fix is to give it
    a real tag convention rather than to teach this function about it."""
    release = _api_get(f"/repos/{ORG}/{repo_name}/releases/latest")
    if not release:
        return None
    return release["tag_name"].removeprefix("v")


def _build_repo_list(overlay: dict) -> list[dict]:
    exclude = set(overlay.get("exclude", [])) | {THIS_REPO}
    curated = overlay.get("repos", {})

    result = []
    for repo in _list_org_repos():
        name = repo["name"]
        if name in exclude:
            continue
        info = curated.get(name, {})
        # #1 (this repo's own prior finding): GitHub's
        # licence detector reports the bare "GPL-3.0"/"AGPL-3.0" for BOTH
        # the -only and -or-later variant -- it can't distinguish them, so
        # repo.license.spdx_id is only a fallback for a repo the overlay
        # hasn't been updated for yet, never the source of truth once it
        # has a curated `license:`.
        api_license = (repo.get("license") or {}).get("spdx_id") or "—"
        result.append({
            "name": name,
            "html_url": repo["html_url"],
            "display_name": info.get("display_name", name),
            "role": info.get("role", repo.get("description") or ""),
            "platform": info.get("platform"),
            "pending_note": info.get("pending_note"),
            "license": info.get("license", api_license),
            "version": _latest_release_tag(name),
            # #2: the taxonomy bug -- every repo used to be forced into
            # "client of repos[0]" regardless of what it actually was.
            # `product` groups repos that are actually part of one thing
            # (trobar-server + its four clients are all `product: trobar`).
            # A repo the overlay hasn't been updated for yet defaults to
            # its OWN name as a singleton product -- it still appears (the
            # #1-era guarantee), just as its own standalone section rather
            # than silently annexed into whichever product happens to sort
            # first. See _group_by_product() below.
            "product": info.get("product", name),
            "_order": info.get("order", float("inf")),
        })

    # Curated order first (data/repos.yaml's own sequence), then anything
    # with no overlay entry yet, alphabetically -- so a brand-new repo is
    # never silently dropped, it just lands at the end until curated.
    result.sort(key=lambda r: (r["_order"], r["name"]))
    for r in result:
        del r["_order"]
    return result


def _group_by_product(repos: list[dict]) -> list[dict]:
    """#2: groups the already product-ordered flat repo list into per-
    product sections, preserving each repo's own relative order.
    First-occurrence order (plain dicts preserve insertion order) gives the
    product groups themselves an implicit order too -- no separate
    "product order" field to keep in sync with each repo's own `order`."""
    groups: dict[str, list[dict]] = {}
    for r in repos:
        groups.setdefault(r["product"], []).append(r)
    return [{"key": product, "repos": rs} for product, rs in groups.items()]


def _licenses_summary(product_groups: list[dict]) -> str:
    """#2: "trobar" keeps its own server-vs-client split -- a real
    distinction for that product specifically (see template.html.j2's "One
    server, N clients") -- but that framing isn't a claim this generator
    can make about a product it knows nothing else about. Every other
    product just contributes its own distinct licence(s) to a flat
    trailing list instead. Derived from each repo's own licence field
    (curated or the API's own report), not written by hand, so it can't
    silently disagree with what's shown elsewhere on the page."""
    parts = []
    for group in product_groups:
        repos = group["repos"]
        if group["key"] == "trobar" and len(repos) > 1:
            server, clients = repos[0], repos[1:]
            parts.append(f"Server {server['license']}")
            client_licenses = sorted({c["license"] for c in clients if c["license"] != "—"})
            if len(client_licenses) == 1:
                parts.append(f"clients {client_licenses[0]}")
            elif client_licenses:
                parts.append("clients: " + ", ".join(client_licenses))
        else:
            # Labeled with the product key, not appended bare -- an
            # unlabeled trailing licence reads as a stutter whenever it
            # happens to match "clients" above (garfin and the Trobar
            # clients both currently say GPL-3.0-or-later).
            group_licenses = sorted({r["license"] for r in repos if r["license"] != "—"})
            if len(group_licenses) == 1:
                parts.append(f"{group['key']} {group_licenses[0]}")
            elif group_licenses:
                parts.append(f"{group['key']}: " + ", ".join(group_licenses))
    return " · ".join(parts)


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site"
    out_dir.mkdir(parents=True, exist_ok=True)

    with (ROOT / "data" / "repos.yaml").open() as fh:
        overlay = yaml.safe_load(fh)

    repos = _build_repo_list(overlay)
    if not repos:
        print("No repos resolved -- refusing to publish an empty page.", file=sys.stderr)
        return 1

    # #2: split by product rather than treating every repo as a Trobar
    # client -- trobar_repos keeps the existing "one server, N clients"
    # table/grid (a real, accurate claim about that product specifically);
    # other_groups renders every other product in its own generic section,
    # so a repo the overlay hasn't caught up to yet still appears (as its
    # own standalone product) instead of being silently mis-annexed.
    product_groups = _group_by_product(repos)
    trobar_repos = next((g["repos"] for g in product_groups if g["key"] == "trobar"), [])
    other_groups = [g for g in product_groups if g["key"] != "trobar"]

    env = Environment(loader=FileSystemLoader(str(ROOT)), autoescape=True)
    template = env.get_template("template.html.j2")
    html = template.render(
        trobar_repos=trobar_repos,
        other_groups=other_groups,
        licenses_summary=_licenses_summary(product_groups),
        generated_at=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    (out_dir / "index.html").write_text(html)

    brand_out = out_dir / "assets" / "brand"
    if brand_out.exists():
        shutil.rmtree(brand_out)
    shutil.copytree(
        ROOT / "assets" / "brand", brand_out,
        ignore=shutil.ignore_patterns("*.license"),
    )

    print(f"Wrote {out_dir / 'index.html'} ({len(repos)} repos).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
