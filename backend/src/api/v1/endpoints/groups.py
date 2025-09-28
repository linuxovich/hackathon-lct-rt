from __future__ import annotations

import asyncio
import httpx
import urllib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File as FAFile, Form, HTTPException
from fastapi import status as http
from fastapi.responses import JSONResponse

from src.api.v1.schemas.group_schemas import GroupOut, GroupPatch
from src.api.v1.schemas.file_schemas import FileOut, FileStatus
from src.utils.common import (
    _gid, _fid, now_iso,
    ensure_group_dirs, group_dir_raw, group_dir_status,
    extract_zip_filtered, atomic_write_json, read_json_file,
)
from src.infra.storage.local_storage import AsyncLocalJsonFileStoreAiofiles, JsonFileStoreConfig
from src.core.configs import configs

store = AsyncLocalJsonFileStoreAiofiles(JsonFileStoreConfig(base_dir=configs.dirs.store))

groups_router = APIRouter(prefix="/groups", tags=["Groups"])

@groups_router.post("/upload-zip", response_model=GroupOut, status_code=http.HTTP_201_CREATED)
async def upload_zip(
    archive: UploadFile = FAFile(...),
    fond: Optional[str] = Form(None),
    opis: Optional[str] = Form(None),
    delo: Optional[str] = Form(None),
):
    group_uuid = _gid()
    ensure_group_dirs(group_uuid)

    # карточка группы в store
    group_doc = {
        "group_uuid": group_uuid,
        "fond": fond, "opis": opis, "delo": delo,
        "created_at": now_iso(),
    }
    await store.create(f"groups/{group_uuid}", group_doc, overwrite=True)

    # сохранить архив и распаковать в raw_data/
    fd, tmp_name = await asyncio.to_thread(lambda: tempfile.mkstemp(prefix="upload_", suffix=".zip"))
    os.close(fd)
    try:
        with open(tmp_name, "wb") as out:
            while True:
                chunk = await archive.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        files = await extract_zip_filtered(Path(tmp_name), group_dir_raw(group_uuid))
    finally:
        try: os.remove(tmp_name)
        except OSError: pass

    file_ids: List[str] = []
    for src in files:
        if not src.is_file():
            continue
        file_uuid = _fid()
        file_ids.append(file_uuid)

        status_doc = {
            "file_uuid": file_uuid,
            "group_uuid": group_uuid,
            "original_name": src.name,
            "raw_path": str(src),
            "status": FileStatus.progress.value,
            "created_at": now_iso(),
        }
        await atomic_write_json(group_dir_status(group_uuid) / f"{file_uuid}.json", status_doc)
        try:
            query = urllib.parse.urlencode( 
                    {"source": f"/out/var/data/groups/{group_uuid}/raw_data/",
                    "dst": f"/out/var/data/groups/{group_uuid}/process/"}
                    )
            httpx.get(f"http://ml-pipeline:8080/?{query}")
        except Exception as e:
            print(f'Errors: {e}')
        await store.create(f"files/{file_uuid}", status_doc, overwrite=True)

    # индекс группы
    await store.create(f"group_index/{group_uuid}", {"files": file_ids}, overwrite=True)

    return GroupOut(group_uuid=group_uuid, fond=fond, opis=opis, delo=delo)


@groups_router.get("/{group_uuid}/files", response_model=List[FileOut])
async def list_files_in_group(group_uuid: str):
    if not await store.exists(f"group_index/{group_uuid}"):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "group not found")
    idx = await store.read(f"group_index/{group_uuid}")
    out: List[FileOut] = []
    for fid in idx.get("files", []):
        s_path = group_dir_status(group_uuid) / f"{fid}.json"
        if not s_path.exists():
            # запись могла быть удалена
            continue
        doc = await read_json_file(s_path)
        out.append(FileOut(
            file_uuid=fid,
            group_uuid=group_uuid,
            filename=doc.get("original_name", ""),
            status=FileStatus(doc.get("status", FileStatus.progress.value)),
        ))
    return out


@groups_router.patch("/{group_uuid}", response_model=GroupOut)
async def patch_group(group_uuid: str, patch: GroupPatch):
    key = f"groups/{group_uuid}"
    if not await store.exists(key):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "group not found")
    rec = await store.read(key)
    for f in ("fond", "opis", "delo"):
        val = getattr(patch, f)
        if val is not None:
            rec[f] = val
    await store.replace(key, rec)
    return GroupOut(group_uuid=group_uuid, fond=rec.get("fond"), opis=rec.get("opis"), delo=rec.get("delo"))


@groups_router.delete("/{group_uuid}", status_code=http.HTTP_204_NO_CONTENT)
async def delete_group(group_uuid: str):
    # удалить папку группы целиком
    root = (configs.dirs.data / "groups" / group_uuid).resolve()
    try:
        if root.exists():
            await asyncio.to_thread(shutil.rmtree, root)
    except Exception:
        # не падаем при частично удалённых структурах
        pass

    # удалить записи в store
    await store.delete(f"groups/{group_uuid}", missing_ok=True)
    if await store.exists(f"group_index/{group_uuid}"):
        idx = await store.read(f"group_index/{group_uuid}")
        for fid in idx.get("files", []):
            await store.delete(f"files/{fid}", missing_ok=True)
        await store.delete(f"group_index/{group_uuid}", missing_ok=True)

    return JSONResponse(status_code=http.HTTP_204_NO_CONTENT, content=None)
