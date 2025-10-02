# ML Pipeline для обработки сканов метрических книг

Автоматизированный пайплайн для обработки сканов метрических книг с использованием машинного обучения. Включает детекцию макета, извлечение текстовых областей и распознавание рукописного текста с помощью нейронных сетей.

## 🚀 Быстрый старт

### Сборка и запуск контейнера

```bash
# 1. Перейти в директорию ML пайплайна
cd ml

# 2. Собрать Docker образ
docker-compose build ml-pipeline

# 3. Запустить обработку изображений
docker-compose run --rm ml-pipeline \
  --source /path/to/input/images \
  --destination /path/to/output/results
```

## 🏗️ Архитектура пайплайна

### Общая схема

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Input Scan    │───▶│  Layout Detection│───▶│ Text Extraction │
│   (JPG/PNG)     │    │     (p2pala)     │    │   (cropping)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Final JSON     │◀───│   OCR Processing │◀───│  Text Regions   │
│   Results       │    │   (Transformer)  │    │   (coordinates) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Компоненты пайплайна

1. **Layout Detection (p2pala)** - нейронная сеть для определения текстовых областей
2. **Text Extraction** - вырезание найденных областей из изображения  
3. **OCR Processing** - распознавание рукописного текста с помощью Transformer модели
4. **Text Concatenation** - объединение и обработка результатов

### Структура данных

```
local_storage/
├── input_scans/          # Исходные сканы (JPG, PNG)
├── cropped_images/       # Нарезанные области с текстом
├── xml_intermediate/     # Промежуточные XML файлы (layout, OCR)
├── results/              # Финальные JSON результаты
└── logs/                 # Логи обработки
```

## 🐳 Docker инструкции

### Сборка образа

```bash
# Из корня проекта
docker-compose build ml-pipeline

# Или напрямую из директории ml/
cd ml/
docker build -t ml-pipeline .
```

### Запуск контейнера

#### 1. Базовый запуск

```bash
docker-compose run --rm ml-pipeline \
  --source /app/source \
  --destination /app/destination
```

#### 2. С монтированием локальных директорий

```bash
docker-compose run --rm \
  -v /path/to/your/images:/app/source \
  -v /path/to/your/results:/app/destination \
  ml-pipeline \
  --source /app/source \
  --destination /app/destination
```

#### 3. Запуск с доступом к локальному хранилищу

```bash
docker-compose run --rm ml-pipeline \
  --source /app/local_storage/input_scans \
  --destination /app/local_storage/results
```

## 📁 Структура проекта

```
ml/
├── Dockerfile              # Конфигурация Docker образа
├── entrypoint.py           # Точка входа для Docker контейнера
├── pipeline_processor.py   # Основной процессор пайплайна
├── storage_manager.py      # Управление локальным хранилищем
├── pyproject.toml          # Зависимости Python
├── models/                 # ML модели
│   ├── transformer_v2.0.pt # OCR модель (файл не хранится в репозитории)
│   └── weights.pth         # Веса для layout detection (файл не хранится в репозитории)
├── ocr.py                  # OCR модуль
├── ocr_page.py            # OCR для страниц
├── p2pala.py              # Layout detection
├── text_concatenator.py   # Объединение текста
├── page_xml/              # XML обработка
├── data/                  # Модули обработки данных
├── utils/                 # Утилиты
└── local_storage/         # Локальное хранилище
    ├── input_scans/
    ├── cropped_images/
    ├── xml_intermediate/
    ├── results/
    └── logs/
```

## 🔧 Конфигурация

### Переменные окружения

```bash
# В docker-compose.yml или при запуске
OMP_NUM_THREADS=4          # Количество потоков для OpenMP
PYTHONUNBUFFERED=1         # Небуферизованный вывод Python
```

### Зависимости

Основные зависимости указаны в `pyproject.toml`:

- `torch==1.4` - PyTorch для ML моделей
- `torchvision==0.5.0` - Computer vision
- `opencv-python==3.4.8.29` - Обработка изображений
- `numpy==1.22.4` - Численные вычисления
- `scipy==1.8.1` - Научные вычисления
- `shapely==1.8.2` - Геометрические операции

## 📊 Формат результатов

### JSON структура

```json
{
  "scan": {
    "id": "00000016_000",
    "image_path": "/path/to/scan.jpg",
    "processing_timestamp": "2024-01-15T10:30:00"
  },
  "regions": [
    {
      "id": "rLk2i_3",
      "type": "paragraph",
      "index": 0,
      "concatenated_text": "Выдано свидетельство о рождении...",
      "coordinates": {
        "min_x": 1162,
        "max_x": 1841,
        "min_y": 768,
        "max_y": 3047,
        "width": 679,
        "height": 2279
      },
      "lines": [
        {
          "id": "l3d5A_0",
          "text": "Выдано",
          "confidence": 0.9988509800529318,
          "coordinates": {
            "crop": {
              "min_x": 1144,
              "max_x": 1228,
              "min_y": 781,
              "max_y": 847
            }
          },
          "cropped_image": {
            "filename": "region_000_000.jpg",
            "path": "local_storage/cropped_images/00000016_000_region_000_000.jpg"
          }
        }
      ]
    }
  ],
  "cropped_images": [
    {
      "filename": "region_000_000.jpg",
      "region_id": "rLk2i_3",
      "line_id": "l3d5A_0",
      "coordinates_on_scan": {
        "min_x": 1144,
        "max_x": 1228,
        "min_y": 781,
        "max_y": 847
      }
    }
  ]
}
```

## 🔗 Интеграция с основным бэкендом

### Запуск из FastAPI

```python
import subprocess
from fastapi import FastAPI, UploadFile

app = FastAPI()

@app.post("/process-scan")
async def process_scan(file: UploadFile, scan_id: str):
    # Сохранить файл
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())
    
    # Запустить ML pipeline
    cmd = [
        "docker-compose", "run", "--rm", "ml-pipeline",
        "--source", temp_path,
        "--destination", "/app/results"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return {"status": "success", "scan_id": scan_id}
    else:
        return {"status": "error", "error": result.stderr}
```

### Прямое использование модулей

```python
from ml_pipeline import PipelineProcessor, LocalStorageManager

# Инициализация
storage_manager = LocalStorageManager()
pipeline_processor = PipelineProcessor()

# Обработка скана
result = pipeline_processor.process_scan(
    image_path="scan.jpg",
    scan_id="scan_001", 
    storage_manager=storage_manager
)

print(f"Найдено {len(result['regions'])} текстовых регионов")
```

## 🐛 Отладка и мониторинг

### Проверка логов

```bash
# Логи обработки
tail -f local_storage/logs/*.log

# Логи Docker контейнера
docker-compose logs ml-pipeline
```

### Информация о хранилище

```python
from storage_manager import LocalStorageManager

storage_manager = LocalStorageManager()
info = storage_manager.get_storage_info()

print(f"Сканов: {info['input_scans_count']}")
print(f"Нарезанных картинок: {info['cropped_images_count']}")
print(f"JSON результатов: {info['json_files_count']}")
print(f"Общий размер: {info['total_size_bytes']} байт")
```

### Очистка данных

```python
# Удаление всех файлов конкретного скана
storage_manager.cleanup_scan("scan_001")

# Очистка всего хранилища
storage_manager.cleanup_all()
```

## 🚨 Устранение неполадок

### Проблемы с Docker

```bash
# Пересборка образа с нуля
docker-compose build --no-cache ml-pipeline

# Проверка размера образа
docker images | grep ml-pipeline

# Очистка неиспользуемых образов
docker system prune -a
```

### Проблемы с моделями

```bash
# Проверить наличие моделей
ls -la models/
# Проверить права доступа
chmod -R 755 models/
```

### Проблемы с памятью

```bash
# Увеличить лимиты Docker
# В docker-compose.yml добавить:
deploy:
  resources:
    limits:
      memory: 8G
    reservations:
      memory: 4G
```