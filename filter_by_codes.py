"""
Фильтр выгрузки складов по codes.txt с дополнением из all_products.json.

Товары с остатком — под своим складом (как в исходной выгрузке).
Товары из списка кодов без остатка — в разделе «Без остатка на складах».
"""

import argparse
import json
from pathlib import Path


def load_codes(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def load_catalog(path: Path) -> dict[str, dict]:
    products = json.loads(path.read_text(encoding="utf-8"))
    by_code: dict[str, dict] = {}
    for product in products:
        code = str(product.get("code", "")).strip()
        if code and code not in by_code:
            by_code[code] = product
    return by_code


def catalog_to_warehouse_product(product: dict) -> dict:
    return {
        "product_id": product["product_id"],
        "name": product.get("name"),
        "code": product.get("code"),
        "price": product.get("price", 0.0),
        "quantity": 0.0,
        "reserved": 0.0,
        "stockDays": 0.0,
        "uom": "шт",
        "image": product.get("image"),
        "category": product.get("category"),
        "cells": [],
    }


def filter_warehouses(
    warehouses: dict,
    codes: set[str],
    catalog: dict[str, dict],
) -> tuple[dict, dict]:
    result: dict = {}
    codes_on_warehouse: set[str] = set()

    for warehouse_name, products in warehouses.items():
        matched = [
            product
            for product in products
            if str(product.get("code", "")).strip() in codes
        ]
        if matched:
            result[warehouse_name] = matched
            codes_on_warehouse.update(
                str(product.get("code", "")).strip() for product in matched
            )

    without_stock = []
    for code in sorted(codes - codes_on_warehouse):
        product = catalog.get(code)
        if product:
            without_stock.append(catalog_to_warehouse_product(product))

    if without_stock:
        result["Без остатка на складах"] = without_stock

    stats = {
        "codes_requested": len(codes),
        "codes_on_warehouse": len(codes_on_warehouse),
        "codes_without_stock": len(without_stock),
        "codes_not_in_catalog": len(codes - codes_on_warehouse - set(catalog)),
        "warehouse_rows": sum(len(products) for name, products in result.items() if name != "Без остатка на складах"),
        "without_stock_rows": len(without_stock),
    }
    return result, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-w",
        "--warehouses",
        default="all_warehouses_2026-05-15_13-26-17.json",
        help="выгрузка складов (app.py)",
    )
    parser.add_argument("-c", "--codes", default="codes.txt")
    parser.add_argument("-p", "--products", default="all_products.json")
    parser.add_argument(
        "-o",
        "--output",
        default="all_warehouses_filtered_by_codes.json",
    )
    args = parser.parse_args()

    codes = load_codes(Path(args.codes))
    warehouses = json.loads(Path(args.warehouses).read_text(encoding="utf-8"))
    catalog = load_catalog(Path(args.products))

    result, stats = filter_warehouses(warehouses, codes, catalog)

    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    print(f"Файл: {args.output}")
    print(f"  кодов в списке: {stats['codes_requested']}")
    print(f"  на складах (уник. кодов): {stats['codes_on_warehouse']}")
    print(f"  строк по складам: {stats['warehouse_rows']}")
    print(f"  без остатка (из каталога): {stats['codes_without_stock']}")
    print(f"  нет в номенклатуре: {stats['codes_not_in_catalog']}")
    print(f"  складов в файле: {len(result)}")


if __name__ == "__main__":
    main()
