<!--
SPDX-FileCopyrightText: 2026 missing-foss

SPDX-License-Identifier: GPL-3.0-or-later
-->

# missing-foss.github.io

The org's landing page, published at <https://missing-foss.github.io/>.

**This page is generated. Don't hand-edit `index.html` — there isn't one
committed here at all.** `.github/workflows/pages.yml` runs `generate.py`
against live GitHub API data (the org's public repos, each one's latest
release) plus `data/repos.yaml`'s small curated overlay, and publishes
whatever that produces. A hand-edit to the page itself would just be
overwritten by the next build — the fix belongs in one of:

- **`data/repos.yaml`** — a repo's display name, one-line role, download
  platform blurb, licence, or display order, and the heading of a product
  made of several repos (`products:`). This is the *only* file meant
  for routine hand-editing. Release versions are not in here: every repo
  tags `vX.Y.Z`, so `generate.py` reads the latest release straight from
  the API and strips the one leading `v`.
- **`template.html.j2`** — the page's actual markup/CSS.
- **`generate.py`** — how API data and the overlay combine.

A repo with no entry in `data/repos.yaml` still appears (role text falls
back to its GitHub description, licence to whatever GitHub's own detector
reports — see the comment in `data/repos.yaml` for why that's only a
fallback, not the source of truth) — add an entry to give it the same
treatment as the others, not to make it show up at all.

## Running it locally

```sh
pip install -r requirements.txt
GITHUB_TOKEN=$(gh auth token) python3 generate.py _site   # token optional, raises the API rate limit
python3 -m http.server -d _site 8000
```

## Design

Built from the org's own brand assets (`assets/brand/`, copied from
[missing-foss/.github](https://github.com/missing-foss/.github)'s
`profile/brand/`, not hotlinked).
