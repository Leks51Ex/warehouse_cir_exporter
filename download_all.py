import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TOKEN = "20f610c1ffb25ba4c63b1bdfa84e27412c51c14f"

LIMIT = 1000
BASE_URL = "https://api.moysklad.ru/api/remap/1.2"
PRODUCTS_URL = f"{BASE_URL}/entity/product?expand=productFolder,images"
IMAGE_WORKERS = 2
IMAGE_RETRIES = 5

API_ERRORS = {
    1061: "Нет доступа к JSON API для этого пользователя. Выдайте права в МойСклад "
    "(Настройки → Пользователи) или создайте новый токен.",
}


def build_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept-Encoding": "gzip",
    }


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    return session


def check_response(response: requests.Response) -> None:
    if response.ok:
        return

    message = f"HTTP {response.status_code}"
    try:
        errors = response.json().get("errors", [])
        if errors:
            error = errors[0]
            code = error.get("code")
            hint = API_ERRORS.get(code, error.get("error", ""))
            message = f"{message}, код {code}: {hint}"
    except (ValueError, AttributeError):
        message = f"{message}: {response.text[:200]}"

    raise requests.HTTPError(message, response=response)


def fetch_all(url, session, headers):
    all_rows = []
    offset = 0

    while True:
        params = {
            "limit": LIMIT,
            "offset": offset,
        }

        response = session.get(url, headers=headers, params=params, timeout=60)
        check_response(response)
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


def image_count(product):
    images = product.get("images") or {}
    return images.get("meta", {}).get("size", 0)


def fetch_image_url(product_id, session, headers):
    url = f"{BASE_URL}/entity/product/{product_id}/images"
    time.sleep(0.25)

    for attempt in range(IMAGE_RETRIES):
        response = session.get(url, headers=headers, params={"limit": 1}, timeout=60)
        if response.status_code == 429:
            time.sleep(1 + attempt * 2)
            continue
        check_response(response)
        rows = response.json().get("rows", [])
        if not rows:
            return product_id, None
        meta = rows[0].get("meta", {})
        return product_id, meta.get("downloadHref") or meta.get("href")

    return product_id, None


def fetch_images(product_ids, session, headers):
    image_urls = {}
    total = len(product_ids)

    with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as executor:
        futures = {
            executor.submit(fetch_image_url, product_id, session, headers): product_id
            for product_id in product_ids
        }
        for index, future in enumerate(as_completed(futures), 1):
            try:
                product_id, image_url = future.result()
            except requests.HTTPError:
                continue
            if image_url:
                image_urls[product_id] = image_url
            if index % 500 == 0 or index == total:
                print(f"  изображения: {index}/{total}", flush=True)

    return image_urls


def extract_price(product):
    sale_prices = product.get("salePrices") or []
    if not sale_prices:
        return 0.0
    return sale_prices[0].get("value", 0.0) / 100.0


def extract_category(product):
    folder = product.get("productFolder")
    if isinstance(folder, dict) and folder.get("name"):
        return folder["name"]

    path_name = product.get("pathName")
    if path_name:
        return path_name.split("/")[-1].strip()

    return None


def map_product(product, image_urls):
    product_id = product["id"]
    return {
        "product_id": product_id,
        "name": product.get("name"),
        "code": product.get("code"),
        "price": extract_price(product),
        "image": image_urls.get(product_id),
        "category": extract_category(product),
    }


def save_products(products_raw, image_urls, output_file):
    products = [map_product(product, image_urls) for product in products_raw]
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    with_images = sum(1 for product in products if product["image"])
    return len(products), with_images


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Выгрузка всей номенклатуры из МойСклад")
    parser.add_argument(
        "--token",
        default=os.environ.get("MOYSKLAD_TOKEN", DEFAULT_TOKEN),
        help="API-токен (или переменная MOYSKLAD_TOKEN)",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="не загружать фото (быстро, image будет null)",
    )
    parser.add_argument("-o", "--output", default="all_products.json")
    args = parser.parse_args()

    token = args.token.strip()
    if not token:
        raise SystemExit("Укажите токен: --token или MOYSKLAD_TOKEN")

    headers = build_headers(token)
    session = create_session()
    output_file = args.output

    print("Загрузка товаров...", flush=True)
    try:
        products_raw = fetch_all(PRODUCTS_URL, session, headers)
    except requests.HTTPError as error:
        raise SystemExit(f"Ошибка API: {error}") from error

    image_urls = {}
    if not args.skip_images:
        product_ids_with_images = [
            product["id"] for product in products_raw if image_count(product) > 0
        ]
        print(f"Товаров с изображениями: {len(product_ids_with_images)}", flush=True)

        total, _ = save_products(products_raw, image_urls, output_file)
        print(f"Каталог сохранён: {total} товаров (без фото) → {output_file}", flush=True)

        if product_ids_with_images:
            print("Загрузка изображений (долго)...", flush=True)
            image_urls = fetch_images(product_ids_with_images, session, headers)
    else:
        print("Пропуск загрузки изображений", flush=True)

    total, with_images = save_products(products_raw, image_urls, output_file)
    print(f"Готово: {total} товаров, {with_images} с фото, файл {output_file}", flush=True)
