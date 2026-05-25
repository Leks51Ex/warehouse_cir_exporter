"""
Выгрузка номенклатуры из missing.txt с разбивкой по складам.

Для каждого артикула ищет позицию в МойСклад (assortment/product/variant),
затем запрашивает остатки по складам (report/stock/bystore).
В выходной JSON только: name, id, code, quantity.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.moysklad.ru/api/remap/1.2"
LIMIT = 1000
REQUEST_PAUSE = 0.2

DEFAULT_TOKEN = "7cff5956956595c9998cc502448ef702c15a38fc"


API_ERRORS = {
    1061: "Нет доступа к JSON API. Выдайте права или укажите другой токен.",
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


def load_missing(path: Path) -> list[dict]:
    entries = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("\t") if part.strip()]
        if not parts:
            continue
        code = parts[0]
        name_hint = parts[1] if len(parts) > 1 else ""
        entries.append({"code": code, "name_hint": name_hint, "line": line_no})
    return entries


def entity_href(meta: dict) -> str | None:
    href = (meta or {}).get("href", "")
    return href.split("?")[0] if href else None


def extract_id(href: str) -> str | None:
    match = re.search(r"/entity/(?:product|variant|bundle)/([^/?]+)", href)
    return match.group(1) if match else None


def find_assortment(session: requests.Session, headers: dict, code: str) -> dict | None:
    endpoints = (
        "assortment",
        "product",
        "variant",
    )
    for entity in endpoints:
        url = f"{BASE_URL}/entity/{entity}"
        response = session.get(
            url,
            headers=headers,
            params={"filter": f"code={code}", "limit": 1},
            timeout=60,
        )
        check_response(response)
        rows = response.json().get("rows", [])
        if rows:
            return rows[0]
        time.sleep(REQUEST_PAUSE)
    return None


def fetch_stock_by_store(
    session: requests.Session,
    headers: dict,
    meta: dict,
) -> list[dict]:
    href = entity_href(meta)
    if not href:
        return []

    entity_type = meta.get("type", "product")
    filter_key = "variant" if entity_type == "variant" else "product"
    stock_filter = f"{filter_key}={href}"

    rows: list[dict] = []
    offset = 0

    while True:
        response = session.get(
            f"{BASE_URL}/report/stock/bystore",
            headers=headers,
            params={
                "filter": stock_filter,
                "stockMode": "nonEmpty",
                "limit": LIMIT,
                "offset": offset,
            },
            timeout=60,
        )
        check_response(response)
        page_rows = response.json().get("rows", [])
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(page_rows) < LIMIT:
            break
        offset += LIMIT
        time.sleep(REQUEST_PAUSE)

    return rows


def collect_store_quantities(stock_rows: list[dict]) -> dict[str, float]:
    by_store: dict[str, float] = {}
    for row in stock_rows:
        for item in row.get("stockByStore") or []:
            store_name = item.get("name")
            quantity = float(item.get("stock") or 0)
            if not store_name or quantity == 0:
                continue
            by_store[store_name] = by_store.get(store_name, 0.0) + quantity
    return by_store


def export_missing(
    session: requests.Session,
    headers: dict,
    entries: list[dict],
) -> tuple[dict, dict]:
    warehouses: dict[str, list[dict]] = {}
    not_found: list[dict] = []
    no_stock: list[dict] = []

    total = len(entries)
    for index, entry in enumerate(entries, 1):
        code = entry["code"]
        print(f"[{index}/{total}] {code}", flush=True)

        assortment = find_assortment(session, headers, code)
        if not assortment:
            not_found.append(
                {
                    "code": code,
                    "name_hint": entry["name_hint"],
                    "line": entry["line"],
                }
            )
            time.sleep(REQUEST_PAUSE)
            continue

        meta = assortment.get("meta", {})
        href = entity_href(meta)
        product_id = extract_id(href or "") or assortment.get("id")
        name = assortment.get("name") or entry["name_hint"]
        api_code = str(assortment.get("code") or code).strip()

        stock_rows = fetch_stock_by_store(session, headers, meta)
        store_qty = collect_store_quantities(stock_rows)

        if not store_qty:
            no_stock.append(
                {
                    "code": api_code,
                    "name": name,
                    "id": product_id,
                    "name_hint": entry["name_hint"],
                }
            )
            time.sleep(REQUEST_PAUSE)
            continue

        item = {
            "name": name,
            "id": product_id,
            "code": api_code,
        }
        for store_name, quantity in sorted(store_qty.items()):
            warehouses.setdefault(store_name, []).append(
                {**item, "quantity": quantity}
            )

        time.sleep(REQUEST_PAUSE)

    for products in warehouses.values():
        products.sort(key=lambda row: (row.get("code") or "", row.get("name") or ""))

    stats = {
        "requested": total,
        "found_with_stock": sum(len(v) for v in warehouses.values()),
        "warehouses": len(warehouses),
        "not_found": len(not_found),
        "no_stock": len(no_stock),
    }
    extras = {}
    if not_found:
        extras["Не найдено в МойСклад"] = not_found
    if no_stock:
        extras["Без остатка на складах"] = no_stock

    result = {**warehouses, **extras}
    return result, stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Выгрузка позиций из missing.txt по складам (МойСклад API)",
    )
    parser.add_argument("-i", "--input", default="missing.txt", help="файл с кодами")
    parser.add_argument(
        "-o",
        "--output",
        default="missing_by_warehouses.json",
        help="выходной JSON",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("MOYSKLAD_TOKEN", DEFAULT_TOKEN),
        help="API-токен (по умолчанию DEFAULT_TOKEN в этом файле)",
    )
    args = parser.parse_args()

    token = args.token.strip()
    if not token:
        raise SystemExit("Укажите токен в DEFAULT_TOKEN или --token")

    input_path = Path(args.input)
    if not input_path.is_file():
        raise SystemExit(f"Файл не найден: {input_path}")

    entries = load_missing(input_path)
    if not entries:
        raise SystemExit(f"В {input_path} нет строк с кодами")

    headers = build_headers(token)
    session = create_session()

    print(f"Позиций в {input_path}: {len(entries)}", flush=True)
    try:
        result, stats = export_missing(session, headers, entries)
    except requests.HTTPError as error:
        raise SystemExit(f"Ошибка API: {error}") from error

    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    print(f"\nФайл: {args.output}")
    print(f"  запрошено кодов: {stats['requested']}")
    print(f"  строк на складах: {stats['found_with_stock']}")
    print(f"  складов: {stats['warehouses']}")
    print(f"  не найдено в API: {stats['not_found']}")
    print(f"  найдено, но без остатка: {stats['no_stock']}")


if __name__ == "__main__":
    main()
