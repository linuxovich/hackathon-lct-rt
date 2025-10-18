# src/api/v1/endpoints/pipeline_callback.py
from pathlib import Path
import httpx, urllib.parse, time, os
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status as http, BackgroundTasks

from src.core.configs import configs
from src.tasks.ml_tasks import start_postproccessing_pipeline
from src.infra.storage.local_storage import AsyncLocalJsonFileStoreAiofiles, JsonFileStoreConfig
from src.api.v1.schemas.file_schemas import FileStatus, FileOut, FileStatusModel
from src.utils.common import group_dir_status, atomic_write_json, _resolve_fid_by_filename

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
store = AsyncLocalJsonFileStoreAiofiles(JsonFileStoreConfig(base_dir=configs.dirs.store))


@router.post("/callback_postprocessing", response_model=FileOut)
async def pipeline_callback(payload: dict):
    gid = payload.get("group_uuid")
    filename = payload.get("filename")
    fid: Optional[str] = payload.get("file_uuid")
    status = payload.get("status")

    if not gid or not filename:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "group_uuid and filename are required")

    if not fid:
        fid = await _resolve_fid_by_filename(gid, filename)
        if not fid:
            raise HTTPException(http.HTTP_404_NOT_FOUND, {"message": "file not found for given filename", "filename": filename})

    meta_key = f"files/{fid}"
    if not await store.exists(meta_key):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")

    meta = await store.read(meta_key)
    meta["status"] = status

    await store.replace(meta_key, meta)
    await atomic_write_json(group_dir_status(gid) / f"{fid}.json", meta)

    return FileOut(file_uuid=fid, group_uuid=gid, filename=meta.get("filename") or "", status=status)

@router.post("/callback_ocr", response_model=FileOut)
async def pipeline_callback(payload: dict, background_tasks: BackgroundTasks):
    gid = payload.get("group_uuid")
    filename = payload.get("filename")
    fid: Optional[str] = payload.get("file_uuid")
    status = payload.get("status")

    if not gid or not filename:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "group_uuid and filename are required")

    if not fid:
        fid = await _resolve_fid_by_filename(gid, filename)
        if not fid:
            raise HTTPException(http.HTTP_404_NOT_FOUND, {"message": "file not found for given filename", "filename": filename})

    meta_key = f"files/{fid}"
    if not await store.exists(meta_key):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")

    meta = await store.read(meta_key)
    meta["status"] = status

    await store.replace(meta_key, meta)
    await atomic_write_json(group_dir_status(gid) / f"{fid}.json", meta)

    if status == "upgrading":
        callback_url = f"http://backend:8000/api/v1/pipeline/callback_postprocessing"
        start_postproccessing_pipeline("http://postprocessing", 8000, "process", "final", gid, callback_url)

    return FileOut(file_uuid=fid, group_uuid=gid, filename=meta.get("filename") or "", status=status)
