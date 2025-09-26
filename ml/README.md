# ML Pipeline для обработки сканов метрических книг

## Быстрый старт

```bash
# 1. Соберите Docker образ
docker-compose build

# 2. Запустите обработку
docker-compose run --rm ml-pipeline \
  --source /app/source \
  --destination /app/destination
```

## Архитектура

Планируемая архитектура с основным бэкендом:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Main Backend  │───▶│  ML Pipeline     │───▶│   Results       │
│   (FastAPI)     │    │  (Docker)        │    │   (JSON)        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

- **Main Backend** - основной сервис, который принимает запросы
- **ML Pipeline** - запускается по требованию для обработки сканов
- **Results** - результаты сохраняются в общем volume

## Описание

Модуль для автоматической обработки сканов метрических книг с использованием машинного обучения. Пайплайн включает детекцию макета, извлечение текстовых областей и распознавание рукописного текста.

## Архитектура

### Компоненты пайплайна

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

### Локальное хранилище

```
local_storage/
├── input_scans/          # Исходные сканы
├── cropped_images/        # Нарезанные картинки с текстом
├── xml_intermediate/      # Промежуточные XML файлы
├── results/              # Финальные JSON результаты
└── logs/                 # Логи обработки
```

## Установка и настройка

### Docker (рекомендуется)

Самый простой способ запуска - через Docker:

```bash
# Соберите образ
docker-compose build

# Запустите обработку
docker-compose run --rm ml-pipeline \
  --source /app/source \
  --destination /app/destination
```


### Локальная установка

#### Зависимости

```bash
pip install torch==1.4 torchvision==0.5.0
pip install opencv-python==3.4.8.29
pip install numpy==1.22.4 scipy==1.8.1 shapely==1.8.2
```

### Структура проекта

```
ml_pipeline/
├── __init__.py
├── storage_manager.py      # Управление локальным хранилищем
├── pipeline_processor.py   # Основной процессор пайплайна
├── entrypoint.py          # Docker entrypoint скрипт
├── Dockerfile              # Docker конфигурация
├── docker-compose.yml      # Docker Compose конфигурация
├── .gitignore              # Git ignore файл
├── models/                 # Модели ML
│   ├── transformer_v2.0.pt
│   └── weights.pth
├── data/                   # Модули обработки данных
├── ocr.py                  # OCR модуль
├── ocr_page.py            # OCR для страниц
├── ocr_parameters.py      # Параметры OCR
├── p2pala.py              # Layout detection
├── page_xml/              # XML обработка
└── utils/                 # Утилиты
```

## Интеграция в основной бэкенд

### 1. Импорт модуля

```python
from ml_pipeline import PipelineProcessor, LocalStorageManager
```

### 2. Инициализация

```python
# Инициализация компонентов
storage_manager = LocalStorageManager(base_path="./data/ml_storage")
pipeline_processor = PipelineProcessor()

# Обработка скана
result = pipeline_processor.process_scan(
    image_path="/path/to/scan.jpg",
    scan_id="unique_scan_id",
    storage_manager=storage_manager
)
```

### 3. API интеграция

```python
from fastapi import FastAPI, UploadFile
from ml_pipeline import PipelineProcessor, LocalStorageManager

app = FastAPI()
storage_manager = LocalStorageManager()
pipeline_processor = PipelineProcessor()

@app.post("/process-scan")
async def process_scan_endpoint(file: UploadFile, scan_id: str):
    # Сохранение загруженного файла
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())
    
    # Обработка через пайплайн
    result = pipeline_processor.process_scan(
        image_path=temp_path,
        scan_id=scan_id,
        storage_manager=storage_manager
    )
    
    return {
        "scan_id": scan_id,
        "status": "processed",
        "regions_count": len(result["regions"]),
        "result_path": f"local_storage/results/{scan_id}_result.json"
    }
```

## Детальное описание этапов пайплайна

### Этап 1: Загрузка и подготовка изображения

```python
def _load_and_prepare_image(self, image_path: str) -> np.ndarray:
    # Загрузка изображения в grayscale
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    # Конвертация в BGR для совместимости с моделями
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img
```

**Что происходит:**
- Загрузка изображения из файла
- Конвертация в нужный цветовой формат
- Сохранение в локальное хранилище

### Этап 2: Детекция макета (Layout Detection)

```python
def _detect_layout(self, image: np.ndarray, image_path: str) -> str:
    # Использование p2pala для определения областей с текстом
    image_basenames_to_images = OrderedDict({image_path: image})
    layout_result = predict_layout(image_basenames_to_images)
    return layout_result[image_path]  # XML с координатами областей
```

**Что происходит:**
- Нейронная сеть анализирует изображение
- Определяет области с текстом (TextRegion)
- Возвращает XML с координатами областей
- Сохраняет XML в `local_storage/xml_intermediate/`

### Этап 3: Извлечение текстовых областей

```python
def _extract_text_regions(self, image, layout_xml, scan_id, storage_manager):
    # Парсинг XML с координатами
    root = ET.fromstring(layout_xml)
    
    for text_region in root.findall('TextRegion'):
        for text_line in text_region.findall('TextLine'):
            # Получение координат
            coords = self._parse_coordinates(coords_str)
            # Вырезание области из изображения
            cropped_image = self._crop_image_region(image, coords)
            # Сохранение в локальное хранилище
            cropped_path = storage_manager.save_cropped_image(
                cropped_image, scan_id, f"{region_id}_{line_id}"
            )
```

**Что происходит:**
- Парсинг XML с координатами областей
- Вырезание каждой текстовой области из изображения
- Сохранение нарезанных картинок в `local_storage/cropped_images/`
- Формирование списка областей для OCR

### Этап 4: OCR обработка

```python
def _process_ocr(self, text_regions: List[Dict]) -> List[Dict]:
    for region in text_regions:
        for line in region['text_lines']:
            if 'cropped_image' in line:
                # Конвертация в grayscale для OCR
                gray_img = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
                # Распознавание текста
                texts, confidences = self.ocr_predictor.predict([gray_img])
                line['text'] = texts[0]
                line['confidence'] = confidences[0]
```

**Что происходит:**
- Загрузка Transformer модели для OCR
- Обработка каждой нарезанной картинки
- Распознавание рукописного текста
- Получение текста и уверенности распознавания

### Этап 5: Формирование результата

```python
def _combine_results(self, scan_id, image_path, ocr_results):
    result = {
        "scan_id": scan_id,
        "original_image_path": image_path,
        "original_image_local_path": f"local_storage/input_scans/{scan_id}.jpg",
        "processing_timestamp": self._get_timestamp(),
        "regions": []
    }
    
    for region_idx, region in enumerate(ocr_results):
        region_data = {
            "region_id": region['region_id'],
            "region_type": region['region_type'],
            "region_index": region_idx,
            "text_lines": []
        }
        
        for line_idx, line in enumerate(region['text_lines']):
            line_data = {
                "line_id": line['line_id'],
                "line_index": line_idx,
                "coordinates": line['coordinates'],
                "text": line.get('text', ''),
                "confidence": line.get('confidence', 0.0),
                "cropped_image_path": line.get('cropped_image_path', ''),
                "cropped_image_filename": f"{scan_id}_region_{region_idx:03d}_{line_idx:03d}.jpg"
            }
            region_data["text_lines"].append(line_data)
        
        result["regions"].append(region_data)
    
    return result
```

**Что происходит:**
- Объединение всех результатов в структурированный JSON
- Добавление метаданных (время обработки, пути к файлам)
- Индексация регионов и строк
- Сохранение финального JSON в `local_storage/results/`

## Использование

### Docker (рекомендуется)

```bash
# Соберите образ
docker-compose build

# Обработка всех изображений в директории
docker-compose run --rm ml-pipeline \
  --source /app/source \
  --destination /app/destination

# Обработка с кастомными путями
docker-compose run --rm ml-pipeline \
  --source /path/to/your/source \
  --destination /path/to/your/destination
```

### Запуск из основного бэкенда

Основной бэкенд может запускать ML pipeline через Docker API:

```python
import subprocess
import os

def run_ml_pipeline(source_dir: str, destination_dir: str):
    """Запуск ML pipeline из основного бэкенда"""
    cmd = [
        "docker-compose", "run", "--rm", "ml-pipeline",
        "--source", source_dir,
        "--destination", destination_dir
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr
```

### Локальный запуск (без Docker)

```bash
# Прямой запуск entrypoint скрипта
python entrypoint.py --source /path/to/source --destination /path/to/destination
```

### Программный интерфейс

```python
from ml_pipeline import PipelineProcessor, LocalStorageManager

# Инициализация
storage_manager = LocalStorageManager()
pipeline_processor = PipelineProcessor()

# Обработка
result = pipeline_processor.process_scan(
    image_path="scan.jpg",
    scan_id="scan_001",
    storage_manager=storage_manager
)

print(f"Найдено {len(result['regions'])} текстовых регионов")
```

## Формат результатов

### JSON структура (нормализованная)

```json
{
  "scan": {
    "id": "scan_001",
    "image_path": "/path/to/scan.jpg",
    "local_path": "local_storage/input_scans/scan_001.jpg",
    "dimensions": {
      "width": 5215,
      "height": 4458
    },
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
        "height": 2279,
        "padding": 10,
        "total_lines": 31,
        "bounding_box": {
          "top_left": {"x": 1162, "y": 768},
          "top_right": {"x": 1841, "y": 768},
          "bottom_left": {"x": 1162, "y": 3047},
          "bottom_right": {"x": 1841, "y": 3047}
        }
      },
      "statistics": {
        "line_breaks_handled": 5,
        "merged_words": 3,
        "total_lines": 8
      },
      "lines": [
        {
          "id": "l3d5A_0",
          "index": 0,
          "text": "Выдано",
          "confidence": 0.9988509800529318,
          "coordinates": {
            "original": "1223,786 1149,789 1151,839 1204,837",
            "crop": {
              "min_x": 1144,
              "max_x": 1228,
              "min_y": 781,
              "max_y": 847,
              "width": 84,
              "height": 66,
              "padding": 5
            }
          },
          "cropped_image": {
            "filename": "region_000_000.jpg",
            "path": "local_storage/cropped_images/scan_001_region_000_000.jpg"
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
        "max_y": 847,
        "width": 84,
        "height": 66
      }
    }
  ]
}
```

### Нормализованная структура данных

#### **Иерархия:**
```
СКАН (scan)
├── РЕГИОН 1 (regions[0])
│   ├── ЛАЙН 1 (lines[0]) → НАРЕЗАННАЯ КАРТИНКА 1
│   ├── ЛАЙН 2 (lines[1]) → НАРЕЗАННАЯ КАРТИНКА 2
│   └── CONCATENATED TEXT: "Лайн1 + Лайн2 + ..."
├── РЕГИОН 2 (regions[1])
│   └── ...
└── CROPPED IMAGES (cropped_images[]) - все нарезанные картинки
```

#### **Преимущества нормализации:**

1. **Четкая иерархия**: Скан → Регионы → Лайны → Нарезанные картинки
2. **Устранение дублирования**: Каждый элемент описан один раз
3. **Легкий поиск**: Понятно, где искать нужную информацию
4. **Масштабируемость**: Легко добавлять новые поля

#### **Координаты:**

- **`coordinates.original`** - исходные координаты лайна из XML (многоугольник)
- **`coordinates.crop`** - координаты нарезки лайна (прямоугольник с отступами)
- **`coordinates_on_scan`** - координаты нарезанной картинки относительно скана
- **`regions[].coordinates`** - координаты региона (агрегация всех лайнов)

**Использование:**
```python
# Нарезка изображения лайна
line_coords = line["coordinates"]["crop"]
cropped = image[line_coords["min_y"]:line_coords["max_y"], line_coords["min_x"]:line_coords["max_x"]]

# Отображение прямоугольника лайна
cv2.rectangle(image, (line_coords["min_x"], line_coords["min_y"], line_coords["width"], line_coords["height"]), (0, 255, 0), 2)

# Отображение прямоугольника региона
region_coords = region["coordinates"]
cv2.rectangle(image, (region_coords["min_x"], region_coords["min_y"], region_coords["width"], region_coords["height"]), (255, 0, 0), 3)

# Поиск нарезанной картинки по ID
for img in result["cropped_images"]:
    if img["line_id"] == "l3d5A_0":
        coords = img["coordinates_on_scan"]
        print(f"Координаты: ({coords['min_x']}, {coords['min_y']}) - ({coords['max_x']}, {coords['max_y']})")

# Работа с bounding box региона
bbox = region["coordinates"]["bounding_box"]
print(f"Регион: {bbox['top_left']} → {bbox['bottom_right']}")
```

### Файловая структура результатов

```
local_storage/
├── input_scans/scan_001.jpg                    # Исходный скан
├── cropped_images/                             # Нарезанные картинки
│   ├── scan_001_region_000_000.jpg
│   ├── scan_001_region_000_001.jpg
│   └── ...
├── xml_intermediate/                           # Промежуточные XML
│   ├── scan_001_layout.xml                    # Layout detection
│   └── scan_001_ocr.xml                       # OCR результаты
├── results/scan_001_result.json                # Финальный JSON
└── logs/scan_001.log                          # Лог обработки
```

## Мониторинг и отладка

### Информация о хранилище

```python
storage_info = storage_manager.get_storage_info()
print(f"Сканов: {storage_info['input_scans_count']}")
print(f"Нарезанных картинок: {storage_info['cropped_images_count']}")
print(f"XML файлов: {storage_info['xml_files_count']}")
print(f"JSON результатов: {storage_info['json_files_count']}")
print(f"Логов: {storage_info['log_files_count']}")
print(f"Общий размер: {storage_info['total_size_bytes']} байт")
```

### Очистка данных

```python
# Удаление всех файлов конкретного скана
storage_manager.cleanup_scan("scan_001")
```