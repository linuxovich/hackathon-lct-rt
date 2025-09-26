from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
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

files_router = APIRouter(prefix="/files", tags=["Files"])


@files_router.patch("/{file_uuid}", response_model=FileOut)
async def patch_file(file_uuid: str, patch: FilePatch):
    # читаем индекс файла из store
    key = f"files/{file_uuid}"
    if not await store.exists(key):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")
    rec = await store.read(key)
    rec["status"] = patch.status.value

    # обновляем статус в группе
    s_path = group_dir_status(rec["group_uuid"]) / f"{file_uuid}.json"
    await atomic_write_json(s_path, rec)
    # и дублируем в store
    await store.replace(key, rec)

    return FileOut(
        file_uuid=rec["file_uuid"],
        group_uuid=rec["group_uuid"],
        filename=rec.get("original_name") or rec.get("filename", ""),
        status=FileStatus(rec["status"]),
    )


@files_router.get("/{file_uuid}/content", response_model=FileContentOut)
async def get_file_content(file_uuid: str, stage: str = Query("process", pattern="^(process|final)$")):
    if not await store.exists(f"files/{file_uuid}"):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")
    meta = await store.read(f"files/{file_uuid}")
    p: Path = stage_dir(meta["group_uuid"], stage) / f"{file_uuid}.json"
    if not p.exists():
        raise HTTPException(http.HTTP_404_NOT_FOUND, "content not found")
    data = await read_json_file(p)
    return FileContentOut(file_uuid=file_uuid, json=data)


@files_router.put("/{file_uuid}/content", response_model=FileContentOut)
async def put_file_content(file_uuid: str, payload: FileContentIn, stage: str = Query("process", pattern="^(process|final)$")):
    if not await store.exists(f"files/{file_uuid}"):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")
    meta = await store.read(f"files/{file_uuid}")

    p: Path = stage_dir(meta["group_uuid"], stage) / f"{file_uuid}.json"
    await atomic_write_json(p, payload.json)

    # при записи в process можно перейти в done
    if stage == "process":
        meta["status"] = FileStatus.done.value
        await store.replace(f"files/{file_uuid}", meta)
        await atomic_write_json(group_dir_status(meta["group_uuid"]) / f"{file_uuid}.json", meta)

    return FileContentOut(file_uuid=file_uuid, json=payload.json)


@files_router.delete("/{file_uuid}/content", status_code=http.HTTP_204_NO_CONTENT)
async def delete_file_content(file_uuid: str, stage: str = Query("process", pattern="^(process|final)$")):
    if not await store.exists(f"files/{file_uuid}"):
        return JSONResponse(status_code=http.HTTP_204_NO_CONTENT, content=None)
    meta = await store.read(f"files/{file_uuid}")
    p: Path = stage_dir(meta["group_uuid"], stage) / f"{file_uuid}.json"
    if p.exists():
        await asyncio.to_thread(p.unlink)
    return JSONResponse(status_code=http.HTTP_204_NO_CONTENT, content=None)

