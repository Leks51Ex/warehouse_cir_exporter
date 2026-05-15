import sys
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import re
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit,
    QProgressBar, QLabel, QListWidget, QListWidgetItem, QAbstractItemView,
    QLineEdit, QHBoxLayout
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

DEFAULT_TOKEN = "cb16ea5d8c5c1965445b884048d00c1fad0a635c"
BASE_URL = "https://api.moysklad.ru/api/remap/1.2"
TIMEOUT = 30


storeList = []

TOKEN = DEFAULT_TOKEN
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def update_headers(token):
    global TOKEN, HEADERS
    TOKEN = token
    HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# ========== Сессия ==========
def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    return session

SESSION = create_session()

def fetch_all_stores():
    all_rows = []
    limit = 1000
    offset = 0
    while True:
        url = f"{BASE_URL}/entity/store?limit={limit}&offset={offset}"
        response = SESSION.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        rows = response.json().get("rows", [])
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    return [{"id": row["id"], "name": row["name"]} for row in all_rows]

def fetch_all_pages(base_url):
    all_rows = []
    limit = 1000
    offset = 0
    while True:
        url = f"{base_url}&limit={limit}&offset={offset}" if "?" in base_url else f"{base_url}?limit={limit}&offset={offset}"
        response = SESSION.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            all_rows.extend(data)
            break
        else:
            rows = data.get("rows", [])
            all_rows.extend(rows)
            if len(rows) < limit:
                break
            offset += limit
    return all_rows

def process_store(store_id):
    url_store = f"{BASE_URL}/entity/store/{store_id}"
    url_stock_all = f"{BASE_URL}/report/stock/all?filter=store={BASE_URL}/entity/store/{store_id}&expand=name,code"
    url_slots = f"{BASE_URL}/entity/store/{store_id}/slots"
    url_by_slot = f"{BASE_URL}/report/stock/byslot/current?filter=storeId={store_id}"

    store_response = SESSION.get(url_store, headers=HEADERS, timeout=TIMEOUT)
    store_json = store_response.json()
    store_name = store_json.get("name", "store")

    slots_all = fetch_all_pages(url_slots)
    slot_names = {slot["id"]: slot.get("name", "Без ячейки") for slot in slots_all}

    rows = fetch_all_pages(url_stock_all)

    byslot_rows = fetch_all_pages(url_by_slot)

    def extract_product_id(meta):
        href = meta.get("href", "")
        match = re.search(r'/entity/product/([^/?]+)', href)
        return match.group(1) if match else None

    products = {}
    for entry in rows:
        meta = entry.get("meta", {})
        product_id = extract_product_id(meta)
        quantity = entry.get("stock", 0)
        price = entry.get("price", 0.0) / 100.0

        if not product_id:
            continue

        if product_id not in products:
            products[product_id] = {
                "product_id": product_id,
                "name": entry.get("name"),
                "code": entry.get("code"),
                "price": price,
                "quantity": quantity,
                "reserved": entry.get("reserve"),
                "stockDays":entry.get("stockDays"),
                "uom": entry.get("uom", {}).get("name") if entry.get("uom") else None,
                "image": entry.get("image", {}).get("meta", {}).get("href") if entry.get("image") else None,
                "category": entry.get("folder", {}).get("name") if entry.get("folder") else None,
                "cells": []
            }

    for entry in byslot_rows:
        product_id = entry.get("assortmentId")
        slot_id = entry.get("slotId")
        quantity = entry.get("stock", 0)
        if not product_id or product_id not in products:
            continue
        cell_name = slot_names.get(slot_id, "Без ячейки")
        existing_cells = [c["cell_name"] for c in products[product_id]["cells"]]
        if cell_name not in existing_cells:
            products[product_id]["cells"].append({
                "cell_name": cell_name,
                "quantity": quantity
            })
        else:
            for cell in products[product_id]["cells"]:
                if cell["cell_name"] == cell_name:
                    cell["quantity"] += quantity

    return store_name, list(products.values())


class Worker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, selected_stores):
        super().__init__()
        self.selected_stores = selected_stores

    def run(self):
        all_stores_data = {}
        total = len(self.selected_stores)
        for i, store in enumerate(self.selected_stores, 1):
            store_id = store["id"]
            store_name_display = store["name"]
            try:
                self.log.emit(f"[{i}/{total}] Обработка {store_name_display}...")
                store_name, merged_data = process_store(store_id)
                all_stores_data[store_name] = merged_data
                self.log.emit(f"Успешно ({store_name})")
            except Exception as e:
                self.log.emit(f"Ошибка: {e}")
            self.progress.emit(int(i / total * 100))
        
        
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        output_filename = f"all_warehouses_{timestamp}.json"

        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_stores_data, f, ensure_ascii=False, indent=4)

        self.log.emit(f"Выгрузка завершена! Файл {output_filename} создан.")
        

        self.finished.emit()


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Warehouse Exporter")
        self.setGeometry(200, 200, 600, 500)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Поле ввода токена
        token_layout = QHBoxLayout()
        self.token_label = QLabel("API токен:")
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Введите токен")
        self.token_input.setText(DEFAULT_TOKEN)
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_show_button = QPushButton("👁️")
        self.token_show_button.setCheckable(True)
        self.token_show_button.clicked.connect(self.toggle_token_visibility)
        self.token_show_button.setFixedWidth(40)
        self.token_apply_button = QPushButton("Применить")
        self.token_apply_button.clicked.connect(self.apply_token)
        self.token_apply_button.setFixedWidth(80)
        token_layout.addWidget(self.token_label)
        token_layout.addWidget(self.token_input)
        token_layout.addWidget(self.token_show_button)
        token_layout.addWidget(self.token_apply_button)
        self.layout.addLayout(token_layout)

        self.label = QLabel("Выберите склады для выгрузки:")
        self.layout.addWidget(self.label)

        # Список складов
        self.store_list_widget = QListWidget()
        self.store_list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        self.layout.addWidget(self.store_list_widget)

        # Кнопка перезагрузки складов
        self.reload_button = QPushButton("Обновить список складов")
        self.reload_button.clicked.connect(self.load_stores)
        self.layout.addWidget(self.reload_button)

        # Кнопка
        self.button = QPushButton("Выгрузить выбранные склады")
        self.button.clicked.connect(self.start_export)
        self.layout.addWidget(self.button)

        # Прогресс
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.progress_bar)

        # Логи
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.layout.addWidget(self.log_area)

        # Загружаем список складов
        self.load_stores()

    def load_stores(self):
        self.log_area.append("Загрузка списка складов...")
        self.store_list_widget.clear()
        try:
            global storeList
            storeList = fetch_all_stores()
            for store in storeList:
                item = QListWidgetItem(store["name"])
                self.store_list_widget.addItem(item)
            self.log_area.append(f"Найдено {len(storeList)} складов")
        except Exception as e:
            self.log_area.append(f"Ошибка загрузки складов: {e}")

    def apply_token(self):
        token = self.token_input.text().strip()
        if token:
            update_headers(token)
            self.log_area.append("Токен обновлён. Перезагрузите список складов.")
        else:
            self.log_area.append("Ошибка: введите корректный токен")

    def on_token_changed(self, text):
        update_headers(text)

    def toggle_token_visibility(self, checked):
        if checked:
            self.token_input.setEchoMode(QLineEdit.Normal)
            self.token_show_button.setText("🙈")
        else:
            self.token_input.setEchoMode(QLineEdit.Password)
            self.token_show_button.setText("👁️")

    def start_export(self):
        selected_indexes = self.store_list_widget.selectedIndexes()
        if not selected_indexes:
            self.log_area.append("Не выбран ни один склад!")
            return

        selected_stores = [storeList[i.row()] for i in selected_indexes]
        self.button.setEnabled(False)
        self.log_area.clear()
        self.worker = Worker(selected_stores)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self.add_log)
        self.worker.finished.connect(self.export_finished)
        self.worker.start()

    def add_log(self, message):
        self.log_area.append(message)

    def export_finished(self):
        self.button.setEnabled(True)
        self.add_log("Процесс завершён!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec_())