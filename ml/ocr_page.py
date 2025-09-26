import xml.etree.cElementTree as ET
import cv2
import numpy as np
from ocr import OCRPredictor


def get_ocr_predictions(line_and_idx_and_img_and_txt):
    ocr_predictor = OCRPredictor()

    images = [image for line, idx, image, txt in line_and_idx_and_img_and_txt]
    text_results, confidences = ocr_predictor.predict(images)

    for i in range(len(line_and_idx_and_img_and_txt)):
        line, idx, img, txt = line_and_idx_and_img_and_txt[i]
        new_txt = text_results[i]
        confidence = confidences[i]
        line_and_idx_and_img_and_txt[i] = line, idx, img, new_txt, confidence
    return line_and_idx_and_img_and_txt


def shape_to_percentile_rectangle(coords):
    x_coords = [item[0] for item in coords]
    y_coords = [item[1] for item in coords]

    min_x = np.ceil(np.percentile(x_coords, 10))
    max_x = np.floor(np.percentile(x_coords, 90))
    min_y = np.ceil(np.percentile(y_coords, 10))
    max_y = np.floor(np.percentile(y_coords, 90))
    return int(min_x), int(min_y), int(max_x), int(max_y)


def extend_rectangle(rect_coords, pitch, image_width, image_height):
    min_x = max(0, rect_coords[0] - pitch)
    min_y = max(0, rect_coords[1] - pitch)
    max_x = min(image_width - 1, rect_coords[2] + pitch)
    max_y = min(image_height - 1, rect_coords[3] + pitch)
    return min_x, min_y, max_x, max_y


def crop_image_by_rectangle_shape(image, rect_coords):
    top_x, top_y, bottom_x, bottom_y = rect_coords
    return image[top_y:bottom_y + 1, top_x:bottom_x + 1]


def get_node_coordinates(string):
    coord_pairs = string.split(" ")
    coords = [(int(coord_pair.split(",")[0]), int(coord_pair.split(",")[1])) for coord_pair in coord_pairs]
    return coords


def process_page_file_with_ocr(xml_content, images, rectangle_pitch=10):
    root = ET.fromstring(xml_content)

    for i, page in enumerate(root.findall('Page')):
        image = images[i]
        img_height, img_width = image.shape
        line_and_idx_and_img_and_txt = []

        i = 0
        for text_region in page.findall('TextRegion'):
            for text_line in text_region.findall('TextLine'):
                coords_string = text_line.find("Coords").attrib["points"]
                coords = get_node_coordinates(coords_string)
                rect_coords = shape_to_percentile_rectangle(coords)
                rect_coords = extend_rectangle(rect_coords, rectangle_pitch, img_width, img_height)
                text_line_img = crop_image_by_rectangle_shape(image, rect_coords)

                el = text_line, str(i), text_line_img, None
                line_and_idx_and_img_and_txt.append(el)
                i += 1

        ocr_results = get_ocr_predictions(line_and_idx_and_img_and_txt)

        # Saving results to XML DOM
        for text_line, idx, img, text_result, confidence in ocr_results:
            new_text_equiv = ET.SubElement(text_line, "TextEquiv")

            new_text_equiv.set("confidence", str(confidence))
            new_unicode_value = ET.SubElement(new_text_equiv, "Unicode")
            new_unicode_value.text = text_result
    return ET.tostring(root, short_empty_elements=False)
