from __future__ import annotations

import os
import asyncio
from pathlib import Path
import mimetypes
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi import status as http

from src.api.v1.schemas.file_schemas import (
    FileOut, FileStatus, FilePatch, FileContentIn, FileContentOut
)
from src.utils.common import (
    stage_dir, group_dir_status, atomic_write_json, read_json_file
)
from src.infra.storage.local_storage import AsyncLocalJsonFileStoreAiofiles, JsonFileStoreConfig
from src.core.configs import configs

store = AsyncLocalJsonFileStoreAiofiles(JsonFileStoreConfig(base_dir=configs.dirs.store))

files_router = APIRouter(prefix="/files", tags=["files"])


async def _resolve_content_path(
    file_uuid: str,
    *,
    stage: str,
    filename: Optional[str] = None,
    must_exist: bool = True,
) -> Path:
    """
    Возвращает путь к JSON-контенту в каталоге stage (progress|done).
    Логика:
      - если задан filename — используем его (добавим .json при необходимости)
      - иначе пробуем {file_uuid}.json
      - иначе ищем по шаблонам, основанным на original_name и/или file_uuid
      - если найдено >1 кандидата — 409
      - если не найдено — 404 (если must_exist=True) или путь по умолчанию (если False)
    """
    if not await store.exists(f"files/{file_uuid}"):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")

    meta = await store.read(f"files/{file_uuid}")
    group_uuid = meta["group_uuid"]
    base: Path = stage_dir(group_uuid, stage)

    # 1) Явное имя
    if filename:
        p = base / filename
        if p.suffix != ".json":
            p = p.with_suffix(".json")
        if must_exist and not p.exists():
            raise HTTPException(http.HTTP_404_NOT_FOUND, f"content file '{p.name}' not found")
        return p

    # 2) {file_uuid}.json
    p_default = base / f"{file_uuid}.json"
    if p_default.exists():
        return p_default

    # 3) По шаблонам
    stem = Path(meta.get("original_name", "")).stem
    patterns: List[str] = []
    if stem:
        patterns += [f"{stem}*_result.json", f"{stem}*.json"]
    patterns += [f"*{file_uuid}*.json"]

    candidates: List[Path] = []
    for patt in patterns:
        candidates.extend([p for p in base.glob(patt) if p.is_file()])

    # Убираем дубликаты
    uniq = list({str(p): p for p in candidates}.values())

    if len(uniq) == 1:
        return uniq[0]

    if len(uniq) == 0:
        if must_exist:
            raise HTTPException(http.HTTP_404_NOT_FOUND, "content not found")
        # для записи по умолчанию вернём {file_uuid}.json
        return p_default

    # >1
    print("multiple candidate content files found")
    return uniq[-1]


@files_router.patch("/{file_uuid}", response_model=FileOut)
async def patch_file(file_uuid: str, patch: FilePatch):
    key = f"files/{file_uuid}"
    if not await store.exists(key):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")
    rec = await store.read(key)
    rec["status"] = patch.status.value

    s_path = group_dir_status(rec["group_uuid"]) / f"{file_uuid}.json"
    await atomic_write_json(s_path, rec)
    await store.replace(key, rec)

    return FileOut(
        file_uuid=rec["file_uuid"],
        group_uuid=rec["group_uuid"],
        filename=rec.get("original_name") or rec.get("filename", ""),
        status=FileStatus(rec["status"]),
    )


@files_router.get("/{file_uuid}/content", response_model=FileContentOut)
async def get_file_content(
    file_uuid: str,
    stage: str = Query("done", pattern="^(progress|upgrading|done)$"),
    filename: str | None = Query(None, description="Явное имя json-файла в каталоге stage"),
):
    p = await _resolve_content_path(file_uuid, stage=stage, filename=filename, must_exist=True)
    data = await read_json_file(p)
    return FileContentOut(file_uuid=file_uuid, json=data)


@files_router.put("/{file_uuid}/content", response_model=FileContentOut)
async def put_file_content(
    file_uuid: str,
    payload: FileContentIn,
    stage: str = Query("done", pattern="^(progress|upgrading|done)$"),
    filename: str | None = Query(None, description="Имя json-файла для записи в каталоге stage"),
):
    # тут must_exist=False — можно создавать новый файл
    p = await _resolve_content_path(file_uuid, stage=stage, filename=filename, must_exist=False)
    await atomic_write_json(p, payload.json)

    # при записи в process логично проставить done
    if stage == "progress":
        meta = await store.read(f"files/{file_uuid}")
        meta["status"] = FileStatus.done.value
        await store.replace(f"files/{file_uuid}", meta)
        await atomic_write_json(group_dir_status(meta["group_uuid"]) / f"{file_uuid}.json", meta)

    return FileContentOut(file_uuid=file_uuid, json=payload.json)


@files_router.delete("/{file_uuid}/content", status_code=http.HTTP_204_NO_CONTENT)
async def delete_file_content(
    file_uuid: str,
    stage: str = Query("progress", pattern="^(progress|upgrading|done)$"),
    filename: str | None = Query(None, description="Имя json-файла для удаления"),
):
    # если must_exist=True и файла нет — вернём 404? Для idempotent delete оставим 204 при отсутствии.
    try:
        p = await _resolve_content_path(file_uuid, stage=stage, filename=filename, must_exist=True)
    except HTTPException as e:
        if e.status_code == http.HTTP_404_NOT_FOUND:
            return JSONResponse(status_code=http.HTTP_204_NO_CONTENT, content=None)
        raise
    if p.exists():
        await asyncio.to_thread(p.unlink)
    return JSONResponse(status_code=http.HTTP_204_NO_CONTENT, content=None)

def _raw_image_path(group_uuid: str, filename: str) -> Path:
    """Безопасно построить путь до исходного изображения в raw_data/."""
    base = (configs.dirs.data / "groups" / group_uuid / "raw_data").resolve()
    p = (base / filename).resolve()
    # защита от выходов за пределы каталога
    if not str(p).startswith(str(base) + os.sep) and p != base:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "bad filename path")
    return p

@files_router.get("/{file_uuid}/image")
async def get_file_image(file_uuid: str):
    """
    Возвращает исходное изображение (из raw_data/) по file_uuid.
    Content-Type ставится по расширению файла.
    """
    key = f"files/{file_uuid}"
    if not await store.exists(key):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")

    meta = await store.read(key)
    group_uuid = meta.get("group_uuid")
    filename = meta.get("filename") or meta.get("original_name")

    if not group_uuid or not filename:
        raise HTTPException(http.HTTP_500_INTERNAL_SERVER_ERROR, "corrupted file metadata")

    img_path = _raw_image_path(group_uuid, filename)
    if not img_path.exists() or not img_path.is_file():
        raise HTTPException(http.HTTP_404_NOT_FOUND, "image not found on disk")

    media_type = mimetypes.guess_type(img_path.name)[0] or "application/octet-stream"
    # inline-отдача (без forced download)
    return FileResponse(path=str(img_path), media_type=media_type, filename=img_path.name)
