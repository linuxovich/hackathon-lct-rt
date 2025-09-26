"""
Pipeline processor for in-memory data transfer between components.
Handles the flow of data through the ML pipeline without external dependencies.
"""

import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from collections import OrderedDict
import xml.etree.ElementTree as ET
from p2pala import predict_layout
from ocr import OCRPredictor
from ocr_page import process_page_file_with_ocr
from text_concatenator import TextConcatenator


class PipelineProcessor:
    """Handles in-memory data processing through the ML pipeline."""
    
    def __init__(self):
        """Initialize the pipeline processor."""
        self.ocr_predictor = None
        self.text_concatenator = TextConcatenator()
        self._initialize_components()
    
    def _initialize_components(self):
        """Initialize ML components."""
        try:
            self.ocr_predictor = OCRPredictor()
            print("OCR predictor initialized successfully")
        except Exception as e:
            print(f"Warning: Could not initialize OCR predictor: {e}")
            self.ocr_predictor = None
    
    def process_scan(self, image_path: str, scan_id: str, storage_manager=None) -> Dict[str, Any]:
        """
        Process a single scan through the complete pipeline.
        
        Args:
            image_path: Path to the input scan image
            scan_id: Unique identifier for the scan
            storage_manager: Local storage manager instance
        
        Returns:
            Dictionary with processing results
        """
        print(f"Processing scan: {scan_id}")
        
        # Step 1: Load and prepare image
        image_data = self._load_and_prepare_image(image_path)
        if image_data is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        # Step 2: Layout detection
        print("Detecting layout...")
        layout_data = self._detect_layout(image_data, image_path)
        
        # Save layout XML to local storage
        if storage_manager:
            layout_xml_path = storage_manager.save_xml_intermediate(layout_data, scan_id, "layout")
            print(f"Layout XML saved to: {layout_xml_path}")
        
        # Step 3: Extract text regions
        print("Extracting text regions...")
        text_regions = self._extract_text_regions(image_data, layout_data, scan_id, storage_manager)
        
        # Step 4: OCR processing
        print("Processing OCR...")
        ocr_results = self._process_ocr(text_regions)
        
        # Save OCR XML to local storage
        if storage_manager:
            # Create OCR XML from results
            ocr_xml = self._create_ocr_xml(ocr_results, scan_id)
            ocr_xml_path = storage_manager.save_xml_intermediate(ocr_xml, scan_id, "ocr")
            print(f"OCR XML saved to: {ocr_xml_path}")
        
        # Step 5: Text concatenation and line break handling
        print("Processing text concatenation...")
        concatenated_result = self.text_concatenator.create_concatenated_json(ocr_results, scan_id)
        
        # Step 6: Combine results
        print("Combining results...")
        final_result = self._combine_results(scan_id, image_path, ocr_results, concatenated_result)
        
        return final_result
    
    def _load_and_prepare_image(self, image_path: str) -> Optional[np.ndarray]:
        """
        Load and prepare image for processing.
        
        Args:
            image_path: Path to the image file
        
        Returns:
            Prepared image as numpy array or None if failed
        """
        try:
            # Load image in grayscale
            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return None
            
            # Convert to BGR for compatibility
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            return img
        except Exception as e:
            print(f"Error loading image {image_path}: {e}")
            return None
    
    def _detect_layout(self, image: np.ndarray, image_path: str) -> str:
        """
        Detect layout using p2pala.
        
        Args:
            image: Input image
            image_path: Path to the image file
        
        Returns:
            Layout XML as string
        """
        try:
            image_basenames_to_images = OrderedDict({image_path: image})
            layout_result = predict_layout(image_basenames_to_images)
            # predict_layout returns a dict, we need the XML string for the image
            return layout_result[image_path]
        except Exception as e:
            print(f"Error in layout detection: {e}")
            raise
    
    def _extract_text_regions(self, image: np.ndarray, layout_xml: str, scan_id: str, storage_manager) -> List[Dict[str, Any]]:
        """
        Extract text regions from layout XML.
        
        Args:
            image: Input image
            layout_xml: Layout XML as string
            scan_id: Unique identifier for the scan
            storage_manager: Local storage manager instance
        
        Returns:
            List of text region data
        """
        try:
            root = ET.fromstring(layout_xml)
            text_regions = []
            
            for page in root.findall('Page'):
                for region_idx, text_region in enumerate(page.findall('TextRegion')):
                    region_data = {
                        'region_id': text_region.get('id', ''),
                        'region_type': text_region.get('type', ''),
                        'text_lines': []
                    }
                    
                    for line_idx, text_line in enumerate(text_region.findall('TextLine')):
                        coords_elem = text_line.find('Coords')
                        if coords_elem is not None:
                            coords_str = coords_elem.get('points', '')
                            coords = self._parse_coordinates(coords_str)
                            
                            # Crop image region
                            cropped_image, crop_coords = self._crop_image_region(image, coords)
                            
                            # Save cropped image to local storage
                            region_id = f"{region_idx:03d}"
                            line_id = f"{line_idx:03d}"
                            cropped_path = storage_manager.save_cropped_image(
                                cropped_image, scan_id, f"{region_id}_{line_id}"
                            )
                            
                            line_data = {
                                'line_id': text_line.get('id', ''),
                                'coordinates': coords_str,
                                'crop_coordinates': crop_coords,  # Add crop coordinates
                                'cropped_image_path': cropped_path,
                                'cropped_image': cropped_image  # Keep in memory for OCR
                            }
                            
                            region_data['text_lines'].append(line_data)
                    
                    text_regions.append(region_data)
            
            return text_regions
        except Exception as e:
            print(f"Error extracting text regions: {e}")
            raise
    
    def _parse_coordinates(self, coords_str: str) -> List[Tuple[int, int]]:
        """
        Parse coordinate string into list of tuples.
        
        Args:
            coords_str: Coordinate string in format "x1,y1 x2,y2 ..."
        
        Returns:
            List of coordinate tuples
        """
        coords = []
        if coords_str:
            coord_pairs = coords_str.split()
            for pair in coord_pairs:
                if ',' in pair:
                    x, y = pair.split(',')
                    coords.append((int(float(x)), int(float(y))))
        return coords
    
    def _crop_image_region(self, image: np.ndarray, coords: List[Tuple[int, int]]) -> Tuple[np.ndarray, Dict[str, int]]:
        """
        Crop image region based on coordinates.
        
        Args:
            image: Input image
            coords: List of coordinate tuples
        
        Returns:
            Tuple of (cropped image region, crop coordinates dict)
        """
        if not coords:
            return image, {}
        
        # Get bounding box
        x_coords = [c[0] for c in coords]
        y_coords = [c[1] for c in coords]
        
        min_x = max(0, min(x_coords))
        max_x = min(image.shape[1], max(x_coords))
        min_y = max(0, min(y_coords))
        max_y = min(image.shape[0], max(y_coords))
        
        # Add some padding
        padding = 5
        min_x = max(0, min_x - padding)
        max_x = min(image.shape[1], max_x + padding)
        min_y = max(0, min_y - padding)
        max_y = min(image.shape[0], max_y + padding)
        
        # Create crop coordinates dict
        crop_coords = {
            "crop_min_x": min_x,
            "crop_max_x": max_x,
            "crop_min_y": min_y,
            "crop_max_y": max_y,
            "crop_width": max_x - min_x,
            "crop_height": max_y - min_y,
            "padding": padding
        }
        
        return image[min_y:max_y, min_x:max_x], crop_coords
    
    def _process_ocr(self, text_regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process OCR on text regions.
        
        Args:
            text_regions: List of text region data
        
        Returns:
            List of processed text regions with OCR results
        """
        if self.ocr_predictor is None:
            print("OCR predictor not available, skipping OCR processing")
            return text_regions
        
        try:
            for region in text_regions:
                for line in region['text_lines']:
                    if 'cropped_image' in line:
                        # Process OCR on cropped image
                        cropped_img = line['cropped_image']
                        if cropped_img.size > 0:
                            # Convert to grayscale for OCR
                            gray_img = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
                            
                            # Run OCR
                            texts, confidences = self.ocr_predictor.predict([gray_img])
                            
                            if texts and confidences:
                                line['text'] = texts[0]
                                line['confidence'] = confidences[0]
                            else:
                                line['text'] = ""
                                line['confidence'] = 0.0
                        else:
                            line['text'] = ""
                            line['confidence'] = 0.0
                    
                    # Keep cropped image in memory for file renaming in _combine_results
                    # Will be removed after file creation
            
            return text_regions
        except Exception as e:
            print(f"Error in OCR processing: {e}")
            return text_regions
    
    def _create_ocr_xml(self, ocr_results: List[Dict[str, Any]], scan_id: str) -> str:
        """
        Create OCR XML from processing results.
        
        Args:
            ocr_results: OCR processing results
            scan_id: Unique identifier for the scan
        
        Returns:
            OCR XML as string
        """
        root = ET.Element("PcGts")
        root.set("xmlns", "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15")
        
        page = ET.SubElement(root, "Page")
        page.set("imageFilename", f"{scan_id}.jpg")
        
        for region in ocr_results:
            text_region = ET.SubElement(page, "TextRegion")
            text_region.set("id", region['region_id'])
            text_region.set("type", region['region_type'])
            
            for line in region['text_lines']:
                text_line = ET.SubElement(text_region, "TextLine")
                text_line.set("id", line['line_id'])
                
                coords = ET.SubElement(text_line, "Coords")
                coords.set("points", line['coordinates'])
                
                text_equiv = ET.SubElement(text_line, "TextEquiv")
                text_equiv.set("confidence", str(line.get('confidence', 0.0)))
                
                unicode_elem = ET.SubElement(text_equiv, "Unicode")
                unicode_elem.text = line.get('text', '')
        
        return ET.tostring(root, encoding='unicode')
    
    def _combine_results(self, scan_id: str, image_path: str, ocr_results: List[Dict[str, Any]], concatenated_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine all results into normalized format.
        
        Args:
            scan_id: Unique identifier for the scan
            image_path: Path to original image
            ocr_results: OCR processing results
            concatenated_result: Text concatenation results
        
        Returns:
            Normalized combined results
        """
        # Get image dimensions
        import cv2
        image = cv2.imread(image_path)
        image_height, image_width = image.shape[:2] if image is not None else (0, 0)
        
        # Build normalized structure
        result = {
            "scan": {
                "id": scan_id,
                "image_path": image_path,
                "local_path": f"local_storage/input_scans/{scan_id}.jpg",
                "dimensions": {
                    "width": image_width,
                    "height": image_height
                },
                "processing_timestamp": self._get_timestamp()
            },
            "regions": [],
            "cropped_images": []
        }
        
        # Process regions
        for region_idx, region in enumerate(ocr_results):
            # Get concatenated text for this region
            concatenated_text = ""
            line_breaks_handled = 0
            merged_words = 0
            
            if region_idx < len(concatenated_result["concatenated_regions"]):
                concat_region = concatenated_result["concatenated_regions"][region_idx]
                concatenated_text = concat_region.get("concatenated_text", "")
                line_breaks_handled = concat_region.get("line_breaks_handled", 0)
                merged_words = concat_region.get("merged_words", 0)
            
            # Calculate region coordinates (aggregation of line coordinates)
            region_coords = self._calculate_region_coordinates(region.get('text_lines', []))
            
            region_data = {
                "id": region['region_id'],
                "type": region['region_type'],
                "index": region_idx,
                "concatenated_text": concatenated_text,
                "coordinates": region_coords,  # Add region coordinates
                "statistics": {
                    "line_breaks_handled": line_breaks_handled,
                    "merged_words": merged_words,
                    "total_lines": len(region.get('text_lines', []))
                },
                "lines": []
            }
            
            # Process lines in this region (keep original order for file-text correspondence)
            for line_idx, line in enumerate(region['text_lines']):
                crop_coords = line.get('crop_coordinates', {})
                
                line_data = {
                    "id": line['line_id'],
                    "index": line_idx,
                    "text": line.get('text', ''),
                    "confidence": line.get('confidence', 0.0),
                    "coordinates": {
                        "original": line['coordinates'],
                        "crop": {
                            "min_x": crop_coords.get('crop_min_x', 0),
                            "max_x": crop_coords.get('crop_max_x', 0),
                            "min_y": crop_coords.get('crop_min_y', 0),
                            "max_y": crop_coords.get('crop_max_y', 0),
                            "width": crop_coords.get('crop_width', 0),
                            "height": crop_coords.get('crop_height', 0),
                            "padding": crop_coords.get('padding', 0)
                        }
                    },
                    "cropped_image": {
                        "filename": f"region_{region_idx:03d}_{line_idx:03d}.jpg",
                        "path": line.get('cropped_image_path', '')
                    }
                }
                
                region_data["lines"].append(line_data)
                
                # Add to cropped_images list
                if crop_coords:
                    cropped_image_info = {
                        "filename": f"region_{region_idx:03d}_{line_idx:03d}.jpg",
                        "region_id": region['region_id'],
                        "line_id": line['line_id'],
                        "coordinates_on_scan": {
                            "min_x": crop_coords.get('crop_min_x', 0),
                            "max_x": crop_coords.get('crop_max_x', 0),
                            "min_y": crop_coords.get('crop_min_y', 0),
                            "max_y": crop_coords.get('crop_max_y', 0),
                            "width": crop_coords.get('crop_width', 0),
                            "height": crop_coords.get('crop_height', 0)
                        }
                    }
                    result["cropped_images"].append(cropped_image_info)
            
            result["regions"].append(region_data)
        
        return result
    
    def _sort_lines_by_y_coordinate(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort lines by Y-coordinate (top to bottom).
        
        Args:
            lines: List of line data
        
        Returns:
            Sorted list of lines
        """
        def get_y_coordinate(line):
            """Get Y-coordinate from line coordinates."""
            coords_str = line.get('coordinates', '')
            if not coords_str:
                return 0
            
            # Parse coordinates and get average Y
            coords = self._parse_coordinates(coords_str)
            if not coords:
                return 0
            
            # Calculate average Y coordinate
            y_coords = [coord[1] for coord in coords]
            return sum(y_coords) / len(y_coords)
        
        # Sort lines by Y-coordinate (top to bottom)
        sorted_lines = sorted(lines, key=get_y_coordinate)
        return sorted_lines
    
    def _calculate_cropped_images_coordinates(self, ocr_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculate coordinates of cropped images (маленьких картинок) relative to scan.
        
        Args:
            ocr_results: OCR processing results
        
        Returns:
            List of cropped image coordinates
        """
        cropped_images = []
        
        for region_idx, region in enumerate(ocr_results):
            for line_idx, line in enumerate(region.get('text_lines', [])):
                crop_coords = line.get('crop_coordinates', {})
                if crop_coords:
                    cropped_image_info = {
                        "region_index": region_idx,
                        "line_index": line_idx,
                        "region_id": region.get('region_id', ''),
                        "line_id": line.get('line_id', ''),
                        "cropped_image_filename": f"region_{region_idx:03d}_{line_idx:03d}.jpg",
                        "coordinates_on_scan": {
                            "min_x": crop_coords.get('crop_min_x', 0),
                            "max_x": crop_coords.get('crop_max_x', 0),
                            "min_y": crop_coords.get('crop_min_y', 0),
                            "max_y": crop_coords.get('crop_max_y', 0),
                            "width": crop_coords.get('crop_width', 0),
                            "height": crop_coords.get('crop_height', 0),
                            "padding": crop_coords.get('padding', 0)
                        }
                    }
                    cropped_images.append(cropped_image_info)
        
        return cropped_images
    
    def _calculate_region_coordinates(self, lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate region coordinates by aggregating line coordinates.
        
        Args:
            lines: List of lines in the region
        
        Returns:
            Region coordinates dict
        """
        if not lines:
            return {}
        
        # Collect all crop coordinates from lines
        all_crop_coords = []
        for line in lines:
            crop_coords = line.get('crop_coordinates', {})
            if crop_coords:
                all_crop_coords.append(crop_coords)
        
        if not all_crop_coords:
            return {}
        
        # Calculate bounding box for the region
        min_x = min(coord.get('crop_min_x', 0) for coord in all_crop_coords)
        max_x = max(coord.get('crop_max_x', 0) for coord in all_crop_coords)
        min_y = min(coord.get('crop_min_y', 0) for coord in all_crop_coords)
        max_y = max(coord.get('crop_max_y', 0) for coord in all_crop_coords)
        
        # Add padding for region
        region_padding = 10  # Larger padding for region
        min_x = max(0, min_x - region_padding)
        max_x = max_x + region_padding
        min_y = max(0, min_y - region_padding)
        max_y = max_y + region_padding
        
        return {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
            "padding": region_padding,
            "total_lines": len(all_crop_coords),
            "bounding_box": {
                "top_left": {"x": min_x, "y": min_y},
                "top_right": {"x": max_x, "y": min_y},
                "bottom_left": {"x": min_x, "y": max_y},
                "bottom_right": {"x": max_x, "y": max_y}
            }
        }
    
    def _get_timestamp(self) -> str:
        """Get current timestamp as string."""
        from datetime import datetime
        return datetime.now().isoformat()
