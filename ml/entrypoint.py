# ml/entrypoint.py
import os
import argparse
from threading import Thread
import json
from pathlib import Path
from typing import List, Dict, Any
import requests
from aiohttp import web

from storage_manager import LocalStorageManager
from pipeline_processor import PipelineProcessor

def parse_arguments():
    parser = argparse.ArgumentParser(description='ML Pipeline Docker Container')
    parser.add_argument('--source', '-s', required=True, help='Source directory containing scan images')
    parser.add_argument('--destination', '-d', required=True, help='Destination directory for output JSON files')
    return parser.parse_args()

def find_image_files(source_dir: str) -> List[str]:
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
    files: List[str] = []
    for ext in list(image_extensions) + [e.upper() for e in image_extensions]:
        files.extend(source_path.rglob(f"*{ext}"))
    return sorted(map(str, files))

def process_single_image(image_path: str, scan_id: str, storage_manager: LocalStorageManager,
                         pipeline_processor: PipelineProcessor) -> Dict[str, Any]:
    return pipeline_processor.process_scan(image_path, scan_id, storage_manager)

def save_result_to_destination(result: Dict[str, Any], scan_id: str, destination_dir: str) -> str:
    dest = Path(destination_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{scan_id}_result.json"
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    return str(out)

def _extract_group_uuid_from_path(p: Path) -> str:
    parts = list(p.resolve().parts)
    if "groups" in parts:
        i = parts.index("groups")
        if i + 1 < len(parts):
            return parts[i + 1]
    return None

def _post_callback(callback_url: str, group_uuid: str, filename: str) -> None:
    if not callback_url:
        return
    payload = {"group_uuid": group_uuid, "filename": filename, "status": "upgrading"}
    # несколько попыток, чтобы не терять событие из-за сетевой загрузки
    backoff = 0.5
    for _ in range(5):
        try:
            r = requests.post(callback_url, json=payload, timeout=10)
            print(f"[callback] POST {callback_url} -> {r.status_code} {r.text[:120]}")
            r.raise_for_status()
            return
        except Exception as e:
            import time
            print(f"[callback] retry after error: {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 8)

def start_image_processing(source: str, dst: str, callback_url: str):
    image_files = find_image_files(source)
    if not image_files:
        print(f"No image files found in {source}")
        return

    storage_manager = LocalStorageManager()
    pipeline_processor = PipelineProcessor()

    group_uuid = _extract_group_uuid_from_path(Path(source))

    for i, image_path in enumerate(image_files):
        try:
            image_filename = Path(image_path).name           # ← имя исходника в raw_data
            scan_id = f"{Path(image_path).stem}_{i:03d}"

            result = process_single_image(image_path, scan_id, storage_manager, pipeline_processor)
            save_result_to_destination(result, scan_id, dst) # ← твой JSON пишет здесь

            # Сразу уведомляем backend: он поменяет статус на "upgrading"
            _post_callback(callback_url, group_uuid, image_filename)

        except Exception as e:
            print(f"Failed to process {image_path}: {e}")

def main(request):
    try:
        source   = request.query.get('source')
        dst      = request.query.get('dst')
        callback = request.query.get('callback')  # ← НОВЫЙ параметр

        Thread(target=start_image_processing, args=(source, dst, callback), daemon=True).start()
        print(f"Source directory: {source}")
        print(f"Destination directory: {dst}")
        return web.json_response({"status": "accepted"}, status=202)
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        return web.json_response({"error": str(e)}, status=500)

if __name__ == "__main__":
    app = web.Application()
    app.add_routes([web.get('/', main)])
    web.run_app(app, port=int(os.getenv("PORT", "8080")))
