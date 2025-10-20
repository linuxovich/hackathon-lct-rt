import os
import glob
import json
import argparse
import uuid
from PIL import Image
import logging

logger = logging.Logger("prepare_dataset")

def parse_args():
    parser = argparse.ArgumentParser(description="Crop images and save corresponding texts from label JSONs.")
    parser.add_argument('--labels_dir', type=str, default='./raw', help='Directory containing JSON label files')
    parser.add_argument('--input_image_dir', type=str, default='./images', help='Directory containing input images')
    parser.add_argument('--destination_dir', type=str, default='./train', help='Destination directory for output images and texts')
    return parser.parse_args()

def find_image(input_image_dir, base_name):
    pattern = os.path.join(input_image_dir, base_name + '.*')
    for path in glob.glob(pattern):
        ext = os.path.splitext(path)[1].lower()
        if ext in {'.jpg', '.jpeg', '.png'}:
            return path
    return None

def prepare_dataset(args) -> dict:
    """
    Готовит датасет из JSON-аннотаций, проходя по всем регионам (regions) в каждом файле
    и сохраняя для каждого региона кроп изображения и соответствующий текст.

    Поддерживает:
      - Новый формат: data["json"]["scan"]["local_path"/"image_path"] + data["json"]["regions"][*]
      - Запасной вариант: путь к картинке как <input_image_dir>/<base>.jpg

    Ожидаемые поля региона:
      region["coordinates"] = {min_x, min_y, max_x, max_y}
      текст берётся из region["corrected_text"] или region["concatenated_text"] (если нет, то пустая строка)
    """
    labels_dir = args.labels_dir
    input_image_dir = args.input_image_dir
    destination_dir = args.destination_dir

    output_img_dir = os.path.join(destination_dir, 'images')
    output_txt_dir = os.path.join(destination_dir, 'texts')
    os.makedirs(output_img_dir, exist_ok=True)
    os.makedirs(output_txt_dir, exist_ok=True)

    total = 0
    json_files = glob.glob(os.path.join(labels_dir, '*.json'))

    for json_path in json_files:
        base_name = os.path.splitext(os.path.basename(json_path))[0]

        # читаем JSON и поддерживаем вложенность "json"
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Failed to read JSON {json_path}: {e}")
            continue

        root = data.get('json', data).get('json')
        img_path = find_image(input_image_dir, base_name)
        if not img_path:
            print(os.listdir(json_path))
            print(f"Image file not found for {json_path}")
            continue

        # открываем изображение один раз на файл
        try:
            img = Image.open(img_path)
        except Exception as e:
            print(f"Failed to open image {img_path}: {e}")
            continue

        regions = root.get('regions', [])

        # Если regions пуст, в целях совместимости можно обработать одиночный crop, если он есть
        if not regions and 'crop' in root:
            c = root['crop']
            regions = [{
                "coordinates": {
                    "min_x": c.get("min_x"), "min_y": c.get("min_y"),
                    "max_x": c.get("max_x"), "max_y": c.get("max_y"),
                },
                "corrected_text": root.get("text", "")
            }]

        if not regions:
            print(f"No regions in {json_path}")
            continue

        for r in regions:
            coords = r.get('coordinates') or {}
            if not {'min_x', 'min_y', 'max_x', 'max_y'} <= set(coords.keys()):
                # пропускаем некорректный регион
                continue

            # координаты могут быть float/str -> приводим к int и клипуем в границы
            try:
                left = int(float(coords['min_x']))
                top = int(float(coords['min_y']))
                right = int(float(coords['max_x']))
                bottom = int(float(coords['max_y']))
            except Exception:
                # некорректные числа — пропускаем регион
                continue

            # клипуем в границы картинки
            left = max(0, min(left, img.width))
            right = max(0, min(right, img.width))
            top = max(0, min(top, img.height))
            bottom = max(0, min(bottom, img.height))

            # валидность прямоугольника
            if right <= left or bottom <= top:
                continue

            try:
                crop = img.crop((left, top, right, bottom))
            except Exception as e:
                print(f"Failed to crop {img_path} [{left},{top},{right},{bottom}]: {e}")
                continue

            crop_filename = f"{uuid.uuid4()}.jpg"
            crop_path = os.path.join(output_img_dir, crop_filename)

            try:
                crop.save(crop_path)
            except Exception as e:
                print(f"Failed to save crop {crop_path}: {e}")
                continue

            text = (r.get('corrected_text') or r.get('concatenated_text') or '').strip()
            txt_filename = crop_filename.replace(".jpg", ".txt")
            txt_path = os.path.join(output_txt_dir, txt_filename)

            try:
                with open(txt_path, 'w', encoding='utf-8') as tf:
                    tf.write(text)
            except Exception as e:
                print(f"Failed to save text {txt_path}: {e}")
                # если текст не сохранился, удалять картинку не будем — просто идём дальше

            total += 1

        # закрываем изображение после обработки файла
        try:
            img.close()
        except Exception:
            pass

    summary = {"text_dir": output_txt_dir, "image_dir": output_img_dir, "total": total}
    logger.info(summary)
    try:
        logger.info(summary)
    except Exception:
        pass
    return summary


if __name__ == "__main__":
    args = parse_args()
    result = prepare_dataset(args)
    print(f"Total new data files: {result}")
