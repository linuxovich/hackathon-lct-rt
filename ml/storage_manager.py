"""
Local storage manager for the ML pipeline.
Handles storage of input scans, cropped images, and final JSON results.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
import cv2
import numpy as np


class LocalStorageManager:
    """Manages local file storage for the ML pipeline."""
    
    def __init__(self, base_path: str = "./local_storage"):
        """
        Initialize local storage manager.
        
        Args:
            base_path: Base directory for local storage
        """
        self.base_path = Path(base_path)
        self.input_scans_path = self.base_path / "input_scans"
        self.cropped_images_path = self.base_path / "cropped_images"
        self.results_path = self.base_path / "results"
        self.xml_intermediate_path = self.base_path / "xml_intermediate"
        self.logs_path = self.base_path / "logs"
        
        # Create directories if they don't exist
        self._create_directories()
    
    def _create_directories(self):
        """Create necessary directories for storage."""
        directories = [
            self.input_scans_path,
            self.cropped_images_path,
            self.results_path,
            self.xml_intermediate_path,
            self.logs_path
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def save_input_scan(self, image_path: str, scan_id: str) -> str:
        """
        Save input scan image to local storage.
        
        Args:
            image_path: Path to the original image
            scan_id: Unique identifier for the scan
            
        Returns:
            Path to saved image in local storage
        """
        # Ensure scan_id is properly formatted
        scan_id = scan_id.replace(' ', '_').lower()
        filename = f"{scan_id}.jpg"
        destination = self.input_scans_path / filename
        
        # Copy image to local storage
        shutil.copy2(image_path, destination)
        
        return str(destination)
    
    def save_cropped_image(self, image: np.ndarray, scan_id: str, region_id: str) -> str:
        """
        Save cropped image to local storage.
        
        Args:
            image: Cropped image as numpy array
            scan_id: Unique identifier for the scan
            region_id: Unique identifier for the region
            
        Returns:
            Path to saved cropped image
        """
        # Ensure IDs are properly formatted
        scan_id = scan_id.replace(' ', '_').lower()
        region_id = region_id.replace(' ', '_').lower()
        filename = f"{scan_id}_region_{region_id}.jpg"
        destination = self.cropped_images_path / filename
        
        # Save image
        cv2.imwrite(str(destination), image)
        
        return str(destination)
    
    def save_xml_intermediate(self, xml_content: str, scan_id: str, stage: str) -> str:
        """
        Save XML intermediate result to local storage.
        
        Args:
            xml_content: XML content as string
            scan_id: Unique identifier for the scan
            stage: Stage of processing (layout, ocr, etc.)
            
        Returns:
            Path to saved XML file
        """
        # Ensure scan_id is properly formatted
        scan_id = scan_id.replace(' ', '_').lower()
        filename = f"{scan_id}_{stage}.xml"
        destination = self.xml_intermediate_path / filename
        
        with open(destination, 'w', encoding='utf-8') as f:
            if isinstance(xml_content, bytes):
                f.write(xml_content.decode('utf-8'))
            else:
                f.write(xml_content)
        
        return str(destination)
    
    def save_final_json(self, data: Dict[str, Any], scan_id: str) -> str:
        """
        Save final JSON result to local storage.
        
        Args:
            data: Final processed data as dictionary
            scan_id: Unique identifier for the scan
            
        Returns:
            Path to saved JSON file
        """
        filename = f"{scan_id}_result.json"
        destination = self.results_path / filename
        
        with open(destination, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return str(destination)
    
    def load_input_scan(self, scan_id: str) -> Optional[np.ndarray]:
        """
        Load input scan image from local storage.
        
        Args:
            scan_id: Unique identifier for the scan
            
        Returns:
            Loaded image as numpy array or None if not found
        """
        filename = f"{scan_id}.jpg"
        source = self.input_scans_path / filename
        
        if not source.exists():
            return None
        
        return cv2.imread(str(source))
    
    def load_cropped_image(self, scan_id: str, region_id: str) -> Optional[np.ndarray]:
        """
        Load cropped image from local storage.
        
        Args:
            scan_id: Unique identifier for the scan
            region_id: Unique identifier for the region
            
        Returns:
            Loaded image as numpy array or None if not found
        """
        filename = f"{scan_id}_{region_id}.jpg"
        source = self.cropped_images_path / filename
        
        if not source.exists():
            return None
        
        return cv2.imread(str(source))
    
    def load_xml_intermediate(self, scan_id: str, stage: str) -> Optional[str]:
        """
        Load XML intermediate result from local storage.
        
        Args:
            scan_id: Unique identifier for the scan
            stage: Stage of processing (layout, ocr, etc.)
            
        Returns:
            XML content as string or None if not found
        """
        filename = f"{scan_id}_{stage}.xml"
        source = self.xml_intermediate_path / filename
        
        if not source.exists():
            return None
        
        with open(source, 'r', encoding='utf-8') as f:
            return f.read()
    
    def load_final_json(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """
        Load final JSON result from local storage.
        
        Args:
            scan_id: Unique identifier for the scan
            
        Returns:
            Final data as dictionary or None if not found
        """
        filename = f"{scan_id}_result.json"
        source = self.results_path / filename
        
        if not source.exists():
            return None
        
        with open(source, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def list_scans(self) -> List[str]:
        """
        List all available scan IDs in local storage.
        
        Returns:
            List of scan IDs
        """
        scan_files = list(self.input_scans_path.glob("*.jpg"))
        return [f.stem for f in scan_files]
    
    def cleanup_scan(self, scan_id: str):
        """
        Clean up all files related to a specific scan.
        
        Args:
            scan_id: Unique identifier for the scan
        """
        # Remove input scan
        input_file = self.input_scans_path / f"{scan_id}.jpg"
        if input_file.exists():
            input_file.unlink()
        
        # Remove cropped images
        cropped_files = self.cropped_images_path.glob(f"{scan_id}_*.jpg")
        for file in cropped_files:
            file.unlink()
        
        # Remove XML intermediate files
        xml_files = self.xml_intermediate_path.glob(f"{scan_id}_*.xml")
        for file in xml_files:
            file.unlink()
        
        # Remove final JSON
        json_file = self.results_path / f"{scan_id}_result.json"
        if json_file.exists():
            json_file.unlink()
    
    def save_log(self, log_content: str, scan_id: str) -> str:
        """
        Save log content to local storage.
        
        Args:
            log_content: Log content as string
            scan_id: Unique identifier for the scan
            
        Returns:
            Path to saved log file
        """
        # Ensure scan_id is properly formatted
        scan_id = scan_id.replace(' ', '_').lower()
        filename = f"{scan_id}.log"
        destination = self.logs_path / filename
        
        with open(destination, 'w', encoding='utf-8') as f:
            f.write(log_content)
        
        return str(destination)
    
    def get_storage_info(self) -> Dict[str, Any]:
        """
        Get information about local storage usage.
        
        Returns:
            Dictionary with storage information
        """
        def get_directory_size(path: Path) -> int:
            """Calculate total size of directory in bytes."""
            total_size = 0
            for file_path in path.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            return total_size
        
        return {
            "base_path": str(self.base_path),
            "input_scans_count": len(list(self.input_scans_path.glob("*.jpg"))),
            "cropped_images_count": len(list(self.cropped_images_path.glob("*.jpg"))),
            "xml_files_count": len(list(self.xml_intermediate_path.glob("*.xml"))),
            "json_files_count": len(list(self.results_path.glob("*.json"))),
            "log_files_count": len(list(self.logs_path.glob("*.log"))),
            "total_size_bytes": sum([
                get_directory_size(self.input_scans_path),
                get_directory_size(self.cropped_images_path),
                get_directory_size(self.xml_intermediate_path),
                get_directory_size(self.results_path),
                get_directory_size(self.logs_path)
            ])
        }
