import requests
import json
import time

TOKEN = "f863a3e2b495019398bb20f990483a2737d6dd4f"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

LIMIT = 1000

def fetch_all(url):
    all_rows = []
    offset = 0

    while True:
        params = {
            "limit": LIMIT,
            "offset": offset
        }

        response = requests.get(url, headers=HEADERS, params=params)
        data = response.json()
        rows = data.get("rows", [])

        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < LIMIT:
            break

        offset += LIMIT
        time.sleep(0.2)

    return all_rows


# 1. ВСЕ товары (даже без остатков)
products = fetch_all("https://api.moysklad.ru/api/remap/1.2/entity/product")

# 2. Остатки (могут быть не для всех)
stocks = fetch_all("https://api.moysklad.ru/api/remap/1.2/report/stock/all?stockMode=all")

# сохраняем все данные без маппинга
with open("all_products_full.json", "w", encoding="utf-8") as f:
    json.dump({
        "products": products,
        "stocks": stocks
    }, f, ensure_ascii=False, indent=2)

print(f"Готово: {len(products)} товаров, {len(stocks)} остатков")