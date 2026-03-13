# Инструкция по сборке для Linux

## Требования
- Linux (x86_64)
- Python 3.8 или выше

---

## Шаг 1: Установка Python (если не установлен)

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip
```

**Fedora:**
```bash
sudo dnf install python3 python3-pip
```

---

## Шаг 2: Установка зависимостей

```bash
pip3 install -r requirements.txt
pip3 install pyinstaller
```

---

## Шаг 3: Сборка приложения

```bash
pyinstaller WarehouseExporter.spec
```

Или через команду:
```bash
pyinstaller --onefile --name WarehouseExporter app.py
```

---

## Шаг 4: Создание архива для распространения

```bash
cd dist
zip WarehouseExporter_linux.zip WarehouseExporter
```

---

## Результат

Готовый файл: `dist/WarehouseExporter_linux.zip`

---

## Как запускать (для конечного пользователя)

1. Распаковать архив:
```bash
unzip WarehouseExporter_linux.zip
```

2. Дать права на выполнение:
```bash
chmod +x WarehouseExporter
```

3. Запустить:
```bash
./WarehouseExporter
```

---

## Важно!

- Собранный файл работает только на **Linux x86_64**
- Требуется совместимая версия glibc (собирайте на системе со старой glibc для лучшей совместимости)
- Размер файла ~50 МБ из-за PyQt5
