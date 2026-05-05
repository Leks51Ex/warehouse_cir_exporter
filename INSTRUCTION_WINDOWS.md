# Инструкция по сборке для Windows

## Требования
- Windows 10/11
- Python 3.8 или выше

---

## Шаг 1: Установка Python

1. Скачайте Python с официального сайта: https://python.org/downloads/
2. Запустите установщик
3. **ВАЖНО:** Отметьте галочку ✅ **"Add Python to PATH"**
4. Нажмите "Install Now"

---

## Шаг 2: Установка зависимостей

Откройте **Command Prompt (cmd)** или **PowerShell** и выполните:

```cmd
cd путь\к\проекту\stremalit_test
```

```cmd
pip install -r requirements.txt
pip install pyinstaller
```

---

## Шаг 3: Сборка приложения

```cmd
python -m PyInstaller .\WarehouseExporter.spec
```

Или через команду:
```cmd
pyinstaller --onefile --noconsole --name WarehouseExporter app.py
```

---

## Шаг 4: Создание архива для распространения

```cmd
cd dist
powershell Compress-Archive -Path WarehouseExporter.exe -DestinationPath WarehouseExporter_windows.zip -Force
```

Или просто заархивируйте файл `WarehouseExporter.exe` через проводник.

---

## Результат

Готовый файл: `dist/WarehouseExporter_windows.zip`

Внутри архива: `WarehouseExporter.exe`

---

## Как запускать (для конечного пользователя)

1. Распаковать архив в любую папку
2. Дважды кликнуть на `WarehouseExporter.exe`

**Всё!** Приложение запустится.

---

## Важно!

- Собранный `.exe` работает на **Windows 10/11 (64-bit)**
- Размер файла ~50-70 МБ из-за PyQt5
- Антивирусы могут ложно срабатывать на PyInstaller — добавьте в исключения

---

## Если нужна иконка

1. Найдите или создайте файл `icon.ico`
2. Отредактируйте `WarehouseExporter.spec`:
   ```python
   icon='icon.ico',  # вместо 'NONE'
   ```
3. Пересоберите проект
