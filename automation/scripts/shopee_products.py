#!/usr/bin/env python3
"""우리 쇼피 스토어 상품 목록을 받아 automation/blogs/shop/products/<key>.yml 로 저장한다 (Actions 에서 실행).

쇼피 공개 웹 API(v4)를 쓴다. 쇼피가 자동 요청을 막으면(403 등) 실패를 그대로 남기고,
그때는 셀러센터 '상품 일괄 수정 → 엑셀 내려받기' 파일을 받아 `--from-xlsx` 로 넣는다.

  python3 automation/scripts/shopee_products.py            # stores 에 있는 나라 전부
  python3 automation/scripts/shopee_products.py --only sg
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "automation" / "blogs" / "shop" / "products"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
PRICE_DIV = 100000  # 쇼피 v4 가격은 10만 배로 들어 있다


def get(url, referer):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", "Referer": referer,
                                               "X-Requested-With": "XMLHttpRequest", "X-API-SOURCE": "pc"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_store(key, store_url):
    p = urllib.parse.urlparse(store_url)
    base, username = f"{p.scheme}://{p.netloc}", p.path.strip("/")
    shop = get(f"{base}/api/v4/shop/get_shop_detail?username={urllib.parse.quote(username)}", store_url)
    data = shop.get("data") or {}
    shopid = data.get("shopid")
    if not shopid:
        raise RuntimeError(f"shop detail 응답에 shopid 없음: {str(shop)[:200]}")
    items, offset = [], 0
    while True:
        q = {"filter_sold_out": 1, "limit": 100, "offset": offset, "order": "desc", "shopid": shopid, "sort_by": "pop", "use_case": 1}
        res = get(f"{base}/api/v4/shop/search_items?" + urllib.parse.urlencode(q), store_url)
        batch = res.get("items") or []
        for it in batch:
            b = it.get("item_basic") or it
            img_host = p.netloc.replace("shopee.", "down-").split(".")[0]
            items.append({
                "id": str(b.get("itemid")), "name": b.get("name", ""),
                "url": f"{base}/product/{shopid}/{b.get('itemid')}",
                "price": (b.get("price") or 0) / PRICE_DIV, "currency": b.get("currency", ""),
                "image": f"https://{img_host}.img.susercontent.com/file/{b['image']}" if b.get("image") else "",
                "sold": b.get("historical_sold"), "rating": (b.get("item_rating") or {}).get("rating_star"),
                "category": "", "specs": [],
            })
        if len(batch) < 100:
            break
        offset += 100
        time.sleep(2)
    # 상품 설명(사양의 근거) — 막히면 이름만으로 둔다
    for it in items[:60]:
        try:
            d = get(f"{base}/api/v4/item/get?itemid={it['id']}&shopid={shopid}", it["url"])
            desc = ((d.get("data") or {}).get("description") or "").strip()
            if desc:
                it["description"] = desc[:3000]
        except Exception as e:
            it["description_error"] = str(e)[:120]
        time.sleep(1.5)
    return {"store": {"name": data.get("name", username), "url": store_url, "shopid": shopid}, "products": items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    a = ap.parse_args()
    stores = yaml.safe_load((OUT / "stores.yml").read_text(encoding="utf-8"))
    failed = False
    for key, s in stores.items():
        if a.only and key != a.only:
            continue
        if not s.get("url") or s.get("hold"):
            print(f"{key}: 건너뜀 ({'보류' if s.get('hold') else '주소 없음'})")
            continue
        try:
            data = fetch_store(key, s["url"])
        except Exception as e:
            failed = True
            print(f"{key}: 실패 — {e}")
            continue
        path = OUT / f"{key}.yml"
        old = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        keep = {p["id"]: p for p in (old or {}).get("products", [])}
        for p in data["products"]:  # 사람이 채운 category·specs 는 유지
            if p["id"] in keep:
                p["category"] = keep[p["id"]].get("category") or p["category"]
                p["specs"] = keep[p["id"]].get("specs") or p["specs"]
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
        print(f"{key}: {data['store']['name']} 상품 {len(data['products'])}개 → {path.relative_to(ROOT)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
