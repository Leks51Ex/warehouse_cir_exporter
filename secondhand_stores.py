import requests
import json

TOKEN = "f863a3e2b495019398bb20f990483a2737d6dd4f"
URL = "https://api.moysklad.ru/api/remap/1.2/entity/store?limit=1000"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

response = requests.get(URL, headers=headers)
response.raise_for_status()

data = response.json()

stores = [
    {
        "id": store["id"],
        "name": store["name"]
    }
    for store in data.get("rows", [])
]

# запись в файл
with open("stores.json", "w", encoding="utf-8") as f:
    json.dump(stores, f, ensure_ascii=False, indent=4)

print(f"Сохранено складов: {len(stores)}")