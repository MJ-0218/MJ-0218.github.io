# Our Shopee store products (per country)

One file per country: `ph.yml`, `sg.yml`, `my.yml`, `vn.yml`, `id.yml`, `th.yml`, `tw.yml`.
Only products listed here may be linked as "our store" in Humid Hours posts.

```yaml
store:
  name: "<store name>"
  url: https://shopee.ph/<shop>
products:
  - id: "<shopee item id>"
    name: "<listing title>"
    url: https://shopee.ph/product/<shopid>/<itemid>
    category: Beauty            # Beauty / Living
    specs:                       # copied from the listing (these are the claims source)
      - "SPF50+ PA++++"
      - "50 ml"
    image: /assets/shop/ph/<file>.jpg   # our own photo (optional)
```
