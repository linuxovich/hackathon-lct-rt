import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web, ClientSession, ClientTimeout, TCPConnector
import aiofiles

from src.processing import process_text


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

completions_router = web.RouteTableDef()

async def on_startup(app: web.Application):
    app['http'] = ClientSession(
    timeout=ClientTimeout(total=15),
    connector=TCPConnector(limit=100, ssl=False)  
    )

async def on_cleanup(app: web.Application):
    await app['http'].close()

def _extract_group_uuid_from_path(p: Path) -> str:
    parts = list(p.resolve().parts)
    if "groups" in parts:
        i = parts.index("groups")
        if i + 1 < len(parts):
            return parts[i + 1]
    return None

async def process_single_file(input_path: Path, output_path: Path, session, callback_url) -> bool:
    """Processes a single JSON file"""

    try:
        logger.info(f"Reading input file: {input_path}")
        async with aiofiles.open(input_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
        
        logger.debug(f"Starting to process file: {input_path.name}")
        processed_data = await process_text(data)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"Saving result to: {output_path}")
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            content = json.dumps(processed_data, ensure_ascii=False, indent=2)
            await f.write(content)
            
        logger.info(f"File {input_path.name} processed successfully!")

        group_uuid = _extract_group_uuid_from_path(Path(input_path))
        filename = input_path.name

        payload = {"group_uuid": group_uuid, "filename": filename, "status": "done"}
        async with session.post(callback_url, json=payload) as resp:
            print(f"Status: {resp.status}")
        return True
        
    except (json.JSONDecodeError, ValueError, Exception) as e:
        logger.error(f"Error processing file {input_path.name}: {e}")
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            content = json.dumps(data, ensure_ascii=False, indent=2)
            await f.write(content)
        return False

    
@completions_router.get('/')
async def process_files(request: web.Request) -> web.Response:
    session: ClientSession = request.app['http']

    input_dir   = request.query.get('source')
    output_dir  = request.query.get('dst')
    callback = request.query.get('callback')

    if not input_dir and not output_dir:
        logger.error("Input and output directories are not specified")
        return web.json_response({'error': 'Input and output directories are not specified'}, status=400)
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not input_path.exists():
        logger.error(f"Input directory not found: {input_path}")
        return web.json_response({'error': f'Input directory not found: {input_path}'}, status=400)
        
    if not input_path.is_dir():
        logger.error(f"Specified path is not a directory: {input_path}")
        return web.json_response({'error': f'Specified path is not a directory: {input_path}'}, status=400)
    
    json_files = list(input_path.glob("*.json"))

    if not json_files:
        logger.warning(f"No JSON files found in {input_path}")
        return web.json_response({'warning': f'No JSON files found in {input_path}'}, status=200)
    
    logger.info(f"Found {len(json_files)} JSON files for processing")

    output_path.mkdir(parents=True, exist_ok=True)

    successful = 0
    failed = 0
    
    for json_file in json_files:
        output_file = output_path / json_file.name
        await process_single_file(json_file, output_file, session, callback)

    return web.json_response({"status_code":200})

def create_app():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.add_routes(completions_router)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host='0.0.0.0', port=8000)

# async def main():
#     input_dir = os.getenv('INPUT_DIR')
#     output_dir = os.getenv('OUTPUT_DIR')
    
#     if not input_dir:
#         logger.error("Не указана входная папка в переменной окружения INPUT_DIR")
#         return
        
#     if not output_dir:
#         logger.error("Не указана выходная папка в переменной окружения OUTPUT_DIR")
#         return
    
#     input_path = Path(input_dir)
#     output_path = Path(output_dir)
    
#     if not input_path.exists():
#         logger.error(f"Входная папка не найдена: {input_path}")
#         return
    
#     if not input_path.is_dir():
#         logger.error(f"Указанный путь не является папкой: {input_path}")
#         return
    
#     # Находим все JSON файлы в папке
#     json_files = list(input_path.glob("*.json"))
    
#     if not json_files:
#         logger.warning(f"В папке {input_path} не найдено JSON файлов")
#         return
    
#     logger.info(f"Найдено {len(json_files)} JSON файлов для обработки")
    
#     # Создаем выходную папку
#     output_path.mkdir(parents=True, exist_ok=True)
    
#     # Обрабатываем каждый файл
#     successful = 0
#     failed = 0
    
#     for json_file in json_files:
#         output_file = output_path / json_file.name
#         if await process_single_file(json_file, output_file):
#             successful += 1
#         else:
#             failed += 1
    
#     logger.info(f"Обработка завершена! Успешно: {successful}, Ошибок: {failed}")


# if __name__ == "__main__":
#     asyncio.run(main())
