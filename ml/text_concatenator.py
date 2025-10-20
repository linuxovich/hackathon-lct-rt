"""
Text concatenation module for handling line breaks and text merging.
Based on concat-analysis logic but adapted for local storage pipeline.
"""

import json
import numpy as np
from typing import Dict, List, Any, Tuple
from collections import OrderedDict
from shapely.geometry import Polygon
import xml.etree.ElementTree as ET


class TextConcatenator:
    """Handles text concatenation and line break processing."""
    
    def __init__(self):
        """Initialize text concatenator."""
        pass
    
    def process_text_concatenation(self, ocr_results: List[Dict[str, Any]], scan_id: str) -> Dict[str, Any]:
        """
        Process OCR results to concatenate text and handle line breaks.
        
        Args:
            ocr_results: OCR processing results
            scan_id: Unique identifier for the scan
        
        Returns:
            Dictionary with concatenated text results
        """
        concatenated_result = {
            "scan_id": scan_id,
            "concatenated_regions": [],
            "processing_timestamp": self._get_timestamp()
        }
        
        for region in ocr_results:
            region_data = {
                "region_id": region['region_id'],
                "region_type": region['region_type'],
                "concatenated_text": "",
                "text_lines": [],
                "line_breaks_handled": 0,
                "merged_words": 0
            }
            
            # Process text lines for concatenation
            text_lines = region['text_lines']
            if not text_lines:
                concatenated_result["concatenated_regions"].append(region_data)
                continue
            
            # Sort lines by Y-coordinate (bottom to top) for proper concatenation
            sorted_lines = self._sort_lines_by_y_coordinate(text_lines)
            
            # Simple concatenation without complex analysis
            concatenated_text = self._simple_concatenate_lines(sorted_lines)
            
            region_data["concatenated_text"] = concatenated_text
            region_data["text_lines"] = text_lines  # Keep original order for file-text correspondence
            region_data["line_breaks_handled"] = 0  # Упрощенная логика
            region_data["merged_words"] = 0  # Упрощенная логика
            
            concatenated_result["concatenated_regions"].append(region_data)
        
        return concatenated_result
    
    def _analyze_text_continuity(self, text_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze text continuity between lines and mark line breaks.
        
        Args:
            text_lines: List of text line data
        
        Returns:
            Processed text lines with continuity information
        """
        processed_lines = []
        
        for i, line in enumerate(text_lines):
            processed_line = line.copy()
            processed_line["is_continuation"] = False
            processed_line["is_line_break"] = False
            processed_line["merged_with_previous"] = False
            
            if i > 0:
                previous_line = processed_lines[-1]
                
                # Check if this line continues the previous one
                if self._is_text_continuous(previous_line["text"], line["text"]):
                    processed_line["is_continuation"] = True
                    processed_line["merged_with_previous"] = True
                    
                    # Handle hyphenated words
                    if previous_line["text"].endswith('-'):
                        # Merge hyphenated word
                        merged_text = previous_line["text"][:-1] + line["text"]
                        processed_line["text"] = merged_text
                        processed_line["merged_text"] = merged_text
                        processed_line["original_text"] = line["text"]
                    else:
                        # Regular continuation
                        processed_line["is_line_break"] = True
                
                # Check for potential line breaks
                elif self._is_potential_line_break(previous_line, line):
                    processed_line["is_line_break"] = True
            
            processed_lines.append(processed_line)
        
        return processed_lines
    
    def _is_text_continuous(self, text1: str, text2: str) -> bool:
        """
        Check if two text strings are continuous (part of same word/sentence).
        
        Args:
            text1: First text string
            text2: Second text string
        
        Returns:
            True if text is continuous
        """
        if not text1 or not text2:
            return False
        
        # Только проверяем переносы через дефис
        if text1.endswith('-') and text2 and not text2[0].isupper():
            return True
        
        return False
    
    def _is_potential_line_break(self, line1: Dict[str, Any], line2: Dict[str, Any]) -> bool:
        """
        Check if there's a potential line break between two lines.
        
        Args:
            line1: First line data
            line2: Second line data
        
        Returns:
            True if potential line break
        """
        # Check coordinate proximity
        coords1 = self._parse_coordinates(line1["coordinates"])
        coords2 = self._parse_coordinates(line2["coordinates"])
        
        if coords1 and coords2:
            # Calculate vertical distance
            y1_avg = sum(coord[1] for coord in coords1) / len(coords1)
            y2_avg = sum(coord[1] for coord in coords2) / len(coords2)
            vertical_distance = abs(y2_avg - y1_avg)
            
            # If lines are close vertically, might be continuation
            if vertical_distance < 50:  # Adjust threshold as needed
                return True
        
        return False
    
    def _concatenate_text_lines(self, processed_lines: List[Dict[str, Any]]) -> str:
        """
        Concatenate processed text lines into final text.
        
        Args:
            processed_lines: Processed text lines with continuity info
        
        Returns:
            Concatenated text string
        """
        # Простое соединение строк в обратном порядке
        text_parts = []
        
        for line in processed_lines:
            text = line.get("text", "").strip()
            if text:
                # Если это перенос через дефис, объединяем с предыдущим
                if line.get("is_continuation") and line.get("merged_text"):
                    if text_parts:
                        text_parts[-1] = line["merged_text"]
                    else:
                        text_parts.append(line["merged_text"])
                else:
                    text_parts.append(text)
        
        return " ".join(text_parts)
    
    def _simple_concatenate_lines(self, text_lines: List[Dict[str, Any]]) -> str:
        """
        Простая конкатенация строк без сложной логики.
        
        Args:
            text_lines: List of text lines
        
        Returns:
            Concatenated text string
        """
        text_parts = []
        
        for line in text_lines:
            text = line.get('text', '').strip()
            if text:
                text_parts.append(text)
        
        return " ".join(text_parts)
    
    def _sort_lines_by_y_coordinate(self, text_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort text lines by Y-coordinate (top to bottom).
        
        Args:
            text_lines: List of text lines
        
        Returns:
            Sorted list of text lines
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
        sorted_lines = sorted(text_lines, key=get_y_coordinate)
        
        return sorted_lines
    
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
    
    def _count_line_breaks_handled(self, processed_lines: List[Dict[str, Any]]) -> int:
        """Count number of line breaks that were handled."""
        return sum(1 for line in processed_lines if line.get("is_line_break", False))
    
    def _count_merged_words(self, processed_lines: List[Dict[str, Any]]) -> int:
        """Count number of words that were merged."""
        return sum(1 for line in processed_lines if line.get("merged_with_previous", False))
    
    def _get_timestamp(self) -> str:
        """Get current timestamp as string."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def create_concatenated_json(self, ocr_results: List[Dict[str, Any]], scan_id: str) -> Dict[str, Any]:
        """
        Create final JSON with concatenated text results.
        
        Args:
            ocr_results: OCR processing results
            scan_id: Unique identifier for the scan
        
        Returns:
            Final JSON with concatenated text
        """
        concatenated_result = self.process_text_concatenation(ocr_results, scan_id)
        
        # Add summary statistics
        total_regions = len(concatenated_result["concatenated_regions"])
        total_line_breaks = sum(region["line_breaks_handled"] for region in concatenated_result["concatenated_regions"])
        total_merged_words = sum(region["merged_words"] for region in concatenated_result["concatenated_regions"])
        
        concatenated_result["summary"] = {
            "total_regions": total_regions,
            "total_line_breaks_handled": total_line_breaks,
            "total_merged_words": total_merged_words,
            "average_line_breaks_per_region": total_line_breaks / total_regions if total_regions > 0 else 0
        }
        
        return concatenated_result
