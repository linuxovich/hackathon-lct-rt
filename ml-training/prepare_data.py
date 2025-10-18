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

def prepare_dataset(args) -> dict:

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
        img_path = os.path.join(input_image_dir, base_name + '.jpg')
        if not os.path.exists(img_path):
            print(f"Image file not found for {json_path}")
            continue

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Extract crop coordinates
        coordinates = data['crop']
        min_x = coordinates['min_x']
        max_x = coordinates['max_x']
        min_y = coordinates['min_y']
        max_y = coordinates['max_y']

        # Open image and crop
        img = Image.open(img_path)
        left, upper, right, lower = min_x, min_y, max_x, max_y
        crop = img.crop((left, upper, right, lower))
        crop_filename = f"{uuid.uuid4()}.jpg"
        crop_path = os.path.join(output_img_dir, crop_filename)
        crop.save(crop_path)

        # Extract text
        text = data.get('text', '').strip()

        # Save text
        txt_filename = crop_filename.replace(".jpg", ".txt")
        txt_path = os.path.join(output_txt_dir, txt_filename)
        with open(txt_path, 'w', encoding='utf-8') as tf:
            tf.write(text)
            total += 1
            
    summary = {"text_dir": output_txt_dir, "image_dir":output_img_dir, "total": total}
    print(summary)
    logger.info(summary)
    return summary

if __name__ == "__main__":
    args = parse_args()
    result = prepare_dataset(args)
    print(f"Total new data files: {result}")