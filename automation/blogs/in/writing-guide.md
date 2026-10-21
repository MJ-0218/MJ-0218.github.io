# Writing guide — India blog (THE TREND DESK_IN · trenddesk-in2026.blogspot.com)

Revenue is AdSense, so the job is **answering what Indians are searching for right now, correctly**.
The method is the same as the US blog (calendar + live radar + quote-level fact checks). Indian topics for Indian readers. Never translate a US or Korean post.
`CLAUDE.md` overrides this file.

## 0. How many and when
- **4–5 posts a day** (config `blogs.in.per_day: 5`). Count today's drafts in `automation/blogs/in/drafts/` by `info_as_of` (IST date) before writing. Stop at 5.
- Actions schedules them automatically: IST 07:00–23:00, about 3 hours apart. Breaking topics (`publish: now`) go out right away.

## 1. What to write (priority order)
1. **Spikes**: `trends/in/latest.json` candidates with `spike` (Google Trends IN, Google News IN). Only when the topic has a practical "what do I need to know/do" angle: a date, an amount, a rule, a deadline or a how-to.
2. **Calendar**: `python3 automation/scripts/calendar_due.py --market in` (PM-KISAN, ITR, bank holidays, LPG price, DA hike, CBSE/JEE/NEET/UPSC, monsoon, Diwali…). Each cycle is one post. Put `cycle:` in front matter.
3. Evergreen explainers tied to a live search (e.g. "How to check PM-KISAN status" when an installment is due).

Skip: politics and party opinion, communal or religious controversy, crime, celebrity private life, health/medical advice, betting, crypto tips, stock tips.
Cricket and entertainment spikes are OK only as schedule/ticket/where-to-watch facts from 2 outlets. No opinions on players.

## 2. Facts first
- Categories `Government Schemes`, `Taxes`, `Banking`, `Exams`, `Weather` need an **official source**: `.gov.in`, `.nic.in`, `rbi.org.in`, `npci.org.in`, `nta.ac.in`, `iocl.com`, PIB (`pib.gov.in`).
- `Trending` and `Holidays` facts without an official page need **two different outlets** (`source2`/`quote2`). Same-group syndication counts as one outlet. Examples of one group: Times of India + Economic Times; NDTV + NDTV Profit.
- Check the **year and the session**. Exam portals keep last year's notices online, so last year's date sheet is the most common trap.
- Amounts in ₹ with Indian grouping (₹1,50,000 or ₹1.5 lakh). The fact checker reads ₹/Rs/INR, lakh and crore.
- If a scheme amount or date is "expected", "likely" or "reported", say so in the title and the first paragraph ("expected, not yet notified"). Never present a rumour as official.

## 3. Voice
- Indian English for Indian readers: clear, warm, practical. Spell the way Indian outlets do (colour, programme; "lakh/crore").
- Answer first. The first two sentences give the date, amount or step the reader searched for.
- Short paragraphs (1–3 sentences). Mix short and long sentences. Contractions are fine.
- Explain official terms once in plain words (e.g. "e-KYC — the online identity check").
- Numbered steps for any process (status check, download, apply). Name the exact portal page.
- No invented experience ("I checked my status and…"). No "In today's fast-paced world", "delve", "comprehensive guide", "in conclusion".
- Emoji: none or at most 2, never in headings or tables.
- Close with one practical line and a short friendly sign-off ("All the best for your exams!", "Happy Diwali, and stay safe!").

## 4. Structure (Blogger + Google Search)
- `title` ≤ 65 characters, searched phrase first, year/installment number when relevant: "PM Kisan 21st Installment: Date, Status Check and eKYC".
- `description` ≤ 150 characters → Blogger search description.
- `permalink`: short lowercase slug.
- `labels`: 3–6 (e.g. PM Kisan, Government Schemes, Farmers).
- 3–6 H2s. One "At a glance" table when there are 3+ dates or amounts. FAQ section (3 Q&As) when people ask follow-ups.
- 450–1,100 words.
- Info card: `cards.summary` (+ optional `table`) via `make_cards.py`. The footer shows the blog name automatically.

## 5. File format
`automation/blogs/in/drafts/in-<slug>.md` + `automation/claims/in-<slug>.yml`

```yaml
---
title: "Bank Holidays November 2026: State-wise List"
description: "..."
category: Banking        # Government Schemes / Taxes / Banking / Exams / Holidays / Weather / Trending
lang: en
blog: in
info_as_of: 2026-10-21
cycle: in-bank-holidays-2026-11      # or trend: "..." for radar topics
publish: now                         # breaking/spike topics only
permalink: bank-holidays-november-2026
labels: [Bank Holidays, RBI, Banking]
cards: { ... }
sources:
  - title: "RBI — Holiday Matrix"
    url: https://www.rbi.org.in/Scripts/HolidayMatrixDisplay.aspx
---
```

## 6. Gates
`verify_claims.py` (with `--fetch` when possible) PASS · `style_check.py` no FAIL · no near-duplicate of another post on this blog (`similarity_check.py` ≤ 0.35 against the closest recent post on the same topic).
