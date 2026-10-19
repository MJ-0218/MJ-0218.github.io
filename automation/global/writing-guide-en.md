# Writing guide — US posts for Google Blogger

Same method as the Korean pipeline (recurring calendar + live radar + quote-level fact checks), but **US topics for US readers**. Never translate a Korean post.

## 0. Facts first
- Every number, date, dollar amount, percentage and deadline in the body or on a card must be backed by a claim in `automation/claims/<slug>.yml` with a verbatim `quote` from the source (`derived` for your own arithmetic).
- Categories `Benefits`, `Taxes`, `Health Insurance`, `Student Aid`, `Housing`, `Elections`, `Recalls` need an official source (`.gov`). If the official page can't be opened from the writing session, read the Actions-fetched copy: `python3 automation/scripts/evidence.py show <URL> <words>`. If it isn't there yet, add the URL to `automation/global/fetch_requests.txt` and hold the post.
- `Trending` posts (non-government spikes) need two different outlets for each fact (`source2`/`quote2`).
- Check the **year**. Last year's dates presented as this year's is the most common error.
- Not legal, tax or medical advice: when a decision depends on personal circumstances, point readers to the official tool or a professional, in one plain sentence.

## 1. Voice — a friendly American blogger
- Answer first. The first two sentences give the date/amount/deadline the reader searched for.
- Conversational and warm, like a knowledgeable neighbor: contractions (you're, it's, don't), second person, short paragraphs (1–3 sentences).
- Vary sentence length. Mix a few 4–6 word sentences with longer ones.
- A little personality is good ("Mark your calendar.", "Here's the short version."), hype is not. Exclamation marks: rare.
- Emoji: none or at most 3, never in headings or tables.
- No invented experiences ("I tried", "when I called SSA…") unless `firsthand: true`.
- Banned AI tells are in `automation/scripts/style_check.py` (`BANNED_EN`): delve, navigate the complexities, comprehensive guide, in conclusion, it's important to note, game-changer, tapestry…
- Close with one short practical line, then a friendly sign-off that fits the topic, e.g. "Good luck with open enrollment, and take care!" — not "I hope this helps".

## 2. Structure (Blogger + Google Search)
- `title`: ≤ 60 characters, the searched phrase near the front, include the year when the info is yearly ("Medicare Open Enrollment 2026: Dates and What to Check").
- `description`: ≤ 150 characters → Blogger "Search description".
- `permalink`: short lowercase slug with hyphens → Blogger "Custom permalink".
- `labels`: 3–6 Blogger labels (spaces allowed).
- 3–6 H2 headings. Mix forms (statement / question / "How to …"). One "Key dates" or "At a glance" table when there are 3+ dates or amounts.
- 450–1,100 words. Depth over length.
- Sources section is added automatically from `sources` (2+ distinct).

## 3. Images
- Info cards only (`cards:` in front matter, rendered by `make_cards.py`), English text, every number on a card backed by claims.
- No photos from news sites, no screenshots of TV, no stock photos without a license entry.
- Federal government works are generally public domain (17 U.S.C. §105), but still don't hotlink their images; make a card instead.

## 3-1. Places
- For any restaurant, venue or office, add a Google Maps search link made with `python3 automation/scripts/map_link.py "<name> <city, state>"`, written as `[📍 Open in Google Maps](url)`. No map screenshots.

## 4. File format
`automation/global/drafts/<slug>.md` — slug starts with `us-`.

```yaml
---
title: "Medicare Open Enrollment 2026: Dates and What to Check"
description: "Medicare Open Enrollment runs Oct. 15–Dec. 7, 2026. Here's what you can change, when coverage starts, and where to compare plans."
category: Health Insurance       # Benefits / Taxes / Health Insurance / Student Aid / Housing / Elections / Recalls / Holidays / Trending
lang: en
info_as_of: 2026-10-19
deadline: 2026-12-07             # only when there is a deadline
cycle: us-medicare-oe-open-2026  # calendar topics; or trend: "..." for radar topics
permalink: medicare-open-enrollment-2026
labels: [Medicare, Open Enrollment, Health Insurance, Seniors]
cards: { ... }
sources:
  - title: "Medicare.gov — Joining a plan"
    url: https://www.medicare.gov/...
---
```
Claims: `automation/claims/<slug>.yml`, same format as Korean posts.
