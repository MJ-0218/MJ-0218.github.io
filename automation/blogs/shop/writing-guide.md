# Writing guide — Humid Hours (Shopee-country beauty & living blogs)

Seven blogs, one brand, one per country:

| key | blog | language | links |
|---|---|---|---|
| ph | Humid Hours PH | English (Philippine usage) | (our PH store: on hold — no products yet) + Lazada when set |
| sg | Humid Hours SG | English (British spelling) | our Shopee SG store + Amazon.sg (when the Associates ID is set) |
| my | Humid Hours MY | English (British spelling) | our Shopee MY store + Lazada |
| vn | Humid Hours VN | Tiếng Việt | our Shopee VN store + Lazada |
| id | Humid Hours ID | Bahasa Indonesia | (no store of ours) Lazada when set — no store posts |
| th | Humid Hours TH | ภาษาไทย | our Shopee TH store + Lazada |
| tw | Humid Hours TW | 繁體中文 (Taiwan usage) | our Shopee TW store |

`CLAUDE.md` overrides this file. Store URLs are in `automation/blogs/shop/products/stores.yml` (tw, th, sg, vn, my active; ph and mx on hold; id none), product lists in `products/<key>.yml` (fetched daily by `shopee-products.yml`), affiliate IDs in `config.yml affiliates:`.
Every post goes through `automation/blogs/review.md` (two review passes + `blog_audit.py`). **Do not put any store or affiliate link that isn't in those files.**

## 0. Concept — why this blog exists
Humid Hours is a beauty and everyday-living notebook for people who live in hot, humid weather. It's an independent curation blog, not a store page.
Every post answers a real question people in that country search: sunscreen that survives sweat, oily skin in the rainy season, mould in wardrobes, drying laundry in monsoon weeks, what K-drama everyone is watching, how a Korean product category works.
The angle that makes it ours: **climate + Korea**. We know Korean beauty and culture, and we write for the tropics.

## 1. Daily mix (per blog)
- **3–4 posts a day** (config `per_day: 4`). Count today's drafts in that blog's folder by `info_as_of` (local date). Stop at 4.
- Mix across the day. Never two of the same type in a row:
  - **Beauty know-how** (Beauty): ingredients, routines, "how to choose" guides for humid weather. Product-agnostic or several brands.
  - **Living info** (Living): rain, haze, heat, mould, laundry, aircon, electricity, local seasonal events. Official sources (weather agency, health ministry, energy regulator).
  - **K-Culture** (K-Culture): K-drama/K-pop releases, concerts in that country, Korean food or travel trends that are spiking there. Two outlets per fact.
  - **Picks** (Picks): curated product lists for one need ("5 sunscreens for oily skin under ₱500"). **Our store's products may appear here**, alongside other brands on Shopee/Lazada/Amazon.
  - **Deals** (Deals): mega-sale calendars (9.9, 10.10, 11.11, 12.12, payday sales) with verified dates, plus what to look for.
- **Our store's products: at most 1 post per day per blog**, and never more than half the items in a Picks list. The rest of the day is non-store content. Readers should feel they found a helpful blog, not an ad.
- Each country's posts are written for that country (local prices, weather, holidays, sale dates, spelling). Don't copy or translate a post between blogs. Two English blogs (PH/SG/MY) may cover the same topic only with different structure and local facts. Run `similarity_check.py` against the other blog's post: ≤ 0.35.

## 2. Honesty rules (legal and Google)
- **Disclosure next to the recommendations** whenever a post has a store or affiliate link: one short italic line right before the first product, in the post's language:
  - en: *Some picks below are from a shop we run, and some links earn us a commission.*
  - vi: *Một số sản phẩm dưới đây đến từ cửa hàng của chúng tôi, và một số liên kết giúp chúng tôi nhận hoa hồng.*
  - id: *Beberapa produk di bawah berasal dari toko kami, dan sebagian tautan memberi kami komisi.*
  - th: *สินค้าบางรายการด้านล่างมาจากร้านของเรา และบางลิงก์เราได้รับค่าคอมมิชชัน*
  - zh-Hant: *以下部分商品來自我們經營的商店，部分連結我們會獲得佣金。*
  `style_check.py` fails a post with shop/affiliate links and no disclosure. Sources: FTC Endorsement Guides, Singapore ASAS interactive-marketing guidelines, Amazon Associates agreement.
- Links to Shopee/Lazada/Amazon get `rel="sponsored nofollow"` automatically when the post is rendered.
- **No fake testing.** We haven't used the products. No "I tried", "after two weeks my skin…", star ratings or before/after claims. Write from the listing specs, ingredients and official/label information: "who it suits", "what to check", "how to use".
- **No medical or drug claims.** Don't say a product treats acne, whitens, cures or heals. Stick to what the label and listing say ("oil-control", "SPF50+ PA++++" only if the listing says so). Health facts (UV, dengue, heat) need official or medical-body sources.
- Prices change. Write "around" with the date checked, or link to the listing without a price.

## 3. Facts
- Same pipeline as the other blogs: every number, date, price, SPF/PA rating, volume or ingredient % needs a claim with a verbatim quote.
- Our store's listings are a valid source for our own products (`source:` the product URL, `quote:` from the listing text in `products/<key>.yml`; add `manual: "store listing"` when the listing page can't be fetched).
- Weather, haze and health facts need official sources (PAGASA, NEA/MSS, MetMalaysia, NCHMF, BMKG, TMD, CWA; health ministries).
- K-Culture: two different outlets per fact (`source2`/`quote2`).

## 4. Voice — soft and friendly, like the Korean posts, in each country's popular-blogger style
- A friendly, knowledgeable friend in that country. Light, practical, a little witty about the weather. Not a salesperson.
- Per-country voice table (greetings, sentence endings, local words to use or avoid) is in `automation/blogs/review.md` 1차. Follow it.
- Answer first. Short paragraphs (1–3 sentences). Lists and small tables are welcome.
- Use the local language naturally. Vietnamese, Indonesian, Thai and Taiwanese-Mandarin posts must read like native blog posts, not translations. Prefer common words over formal ones, and use local units and currency (₫, Rp, ฿, NT$, ₱, S$, RM).
- Emoji: at most 3, never in headings or tables.
- Sign-off: one short line about the weather or the day, in the post's language.

## 5. Images
- Info cards from `make_cards.py` (footer shows the blog name).
- **Our own store's product photos** are allowed: add each to front matter `images:` with `license: "own store photo"` and `credit: "<store name>"`. Never use other sellers' photos, brand press images or review photos.

## 6. File format
`automation/blogs/<key>/drafts/<key>-<slug>.md` + `automation/claims/<key>-<slug>.yml`

```yaml
---
title: "Sunscreen for Oily Skin in Rainy Season: What to Look For"
description: "..."
category: Beauty          # Beauty / Living / K-Culture / Picks / Deals
lang: en                  # en / vi / id / th / zh-Hant
blog: ph
info_as_of: 2026-10-21
trend: "..."              # when it came from the radar
store: true               # only when our store's products appear
permalink: sunscreen-oily-skin-rainy-season
labels: [Sunscreen, Oily Skin, Skincare]
cards: { ... }
images: []                # our store photos only, with license/credit
sources:
  - title: "..."
    url: https://...
---
```

## 7. Gates
`verify_claims.py` PASS · `style_check.py` no FAIL (disclosure, fake testing, emoji) · cross-blog similarity ≤ 0.35 · store posts ≤ 1/day/blog.
