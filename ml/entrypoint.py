#!/usr/bin/env python3
"""
Docker entrypoint script for ML pipeline processing.
Handles source and destination parameters for batch processing.
"""

import os
import sys
import argparse
from threading import Thread
import json
from pathlib import Path
from typing import List, Dict, Any
import cv2
import numpy as np
from aiohttp import web

from storage_manager import LocalStorageManager
from pipeline_processor import PipelineProcessor


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='ML Pipeline Docker Container')
    parser.add_argument('--source', '-s', required=True, 
                       help='Source directory containing scan images')
    parser.add_argument('--destination', '-d', required=True,
                       help='Destination directory for output JSON files')
    
    return parser.parse_args()


def find_image_files(source_dir: str) -> List[str]:
    """
    Find image files in source directory.
    
    Args:
        source_dir: Source directory path
        
    Returns:
        List of image file paths
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
    
    # Find all image files recursively
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(source_path.rglob(f"*{ext}"))
        image_files.extend(source_path.rglob(f"*{ext.upper()}"))
    
    return sorted([str(f) for f in image_files])


def process_single_image(image_path: str, scan_id: str, storage_manager: LocalStorageManager, 
                        pipeline_processor: PipelineProcessor) -> Dict[str, Any]:
    """
    Process a single image through the pipeline.
    
    Args:
        image_path: Path to the input image
        scan_id: Unique identifier for the scan
        storage_manager: Storage manager instance
        pipeline_processor: Pipeline processor instance
        
    Returns:
        Processing result dictionary
    """
    print(f"Processing: {image_path}")
    
    try:
        # Process scan through pipeline directly
        result = pipeline_processor.process_scan(image_path, scan_id, storage_manager)
        print(f"Found {len(result.get('regions', []))} text regions")
        
        return result
        
    except Exception as e:
        print(f"Error processing {image_path}: {str(e)}")
        raise


def save_result_to_destination(result: Dict[str, Any], scan_id: str, destination_dir: str) -> str:
    """
    Save result JSON to destination directory.
    
    Args:
        result: Processing result dictionary
        scan_id: Scan identifier
        destination_dir: Destination directory path
        
    Returns:
        Path to saved JSON file
    """
    destination_path = Path(destination_dir)
    destination_path.mkdir(parents=True, exist_ok=True)
    
    # Create filename based on scan_id
    json_filename = f"{scan_id}_result.json"
    json_path = destination_path / json_filename
    
    # Save JSON with proper formatting
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return str(json_path)

def start_image_processing(source, dst):
    image_files = find_image_files(source)
    
    if not image_files:
        print(f"No image files found in {source}")
        return 1
    
    print(f"Found {len(image_files)} image files to process")
    
    # Initialize components
    storage_manager = LocalStorageManager()
    pipeline_processor = PipelineProcessor()
    
    # Process each image
    successful_count = 0
    failed_count = 0
    
    for i, image_path in enumerate(image_files):
        try:
            # Generate scan ID from filename
            image_filename = Path(image_path).stem
            scan_id = f"{image_filename}_{i:03d}"
            
            print(f"\nProcessing {i+1}/{len(image_files)}: {image_path}")
            
            # Process the image
            result = process_single_image(
                image_path, scan_id, storage_manager, 
                pipeline_processor
            )
            
            # Save result to destination directory
            output_path = save_result_to_destination(result, scan_id, dst)
            print(f"Result saved to: {output_path}")
            
            successful_count += 1
            
        except Exception as e:
            print(f"Failed to process {image_path}: {str(e)}")
            failed_count += 1
            continue
        
        # Print summary
        print(f"\nProcessing complete!")
        print(f"Successfully processed: {successful_count}")
        print(f"Failed: {failed_count}")
        print(f"Total: {len(image_files)}")
        
        return 0 if failed_count == 0 else 1
        

def main(request):
    """Main entrypoint function."""
    try:
        # Parse command line arguments
        # args = parse_arguments()
        source = request.query.get('source')
        dst = request.query.get('dst')

        thread = Thread(target = start_image_processing, args = (source, dst))
        thread.start()
        print(f"Source directory: {source}")
        print(f"Destination directory: {dst}")
        
        # Find image files

    except Exception as e:
        print(f"Fatal error: {str(e)}")
        return 1

if __name__ == "__main__":
    app = web.Application()
    app.add_routes([web.get('/', main)])
    web.run_app(app)
