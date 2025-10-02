from __future__ import annotations

import asyncio
import httpx
import urllib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Literal

from fastapi import APIRouter, UploadFile, Query, File as FAFile, Form, HTTPException
from fastapi import status as http
from fastapi.responses import JSONResponse

from src.api.v1.schemas.group_schemas import GroupOut, GroupPatch
from src.api.v1.schemas.file_schemas import FileOut, FileStatus
from src.utils.common import (
    _gid, _fid, now_iso,
    ensure_group_dirs, group_dir_raw, group_dir_status,
    extract_zip_filtered, atomic_write_json, read_json_file,
)
from src.utils.groups import _save_upload_to_path, _append_group_index, _should_accept

from src.infra.storage.local_storage import AsyncLocalJsonFileStoreAiofiles, JsonFileStoreConfig
from src.tasks.ml_tasks import start_ml_pipeline
from src.core.configs import configs
from src.services.report.report import ReportBuilder

store = AsyncLocalJsonFileStoreAiofiles(JsonFileStoreConfig(base_dir=configs.dirs.store))

groups_router = APIRouter(prefix="/groups", tags=["Groups"])

Format = Literal["xlsx", "csv"]
Stage  = Literal["progress", "done"]


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
        except OSError as e: print(f"Error: {e}")

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
        await store.create(f"files/{file_uuid}", status_doc, overwrite=True)
        start_ml_pipeline.send(group_uuid)
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


@groups_router.get("/{group_uuid}", response_model=GroupOut)
async def get_group(group_uuid: str):
    key = f"groups/{group_uuid}"
    if not await store.exists(key):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "group not found")
    rec = await store.read(key)
    return GroupOut(group_uuid=group_uuid, fond=rec.get("fond"), opis=rec.get("opis"), delo=rec.get("delo"))

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

@groups_router.post("/{group_uuid}/upload-files", response_model=List[FileOut], status_code=http.HTTP_201_CREATED)
async def upload_files_to_group(
    group_uuid: str,
    files: List[UploadFile] = FAFile(..., description="Один или несколько файлов")
):
    group_key = f"groups/{group_uuid}"
    if not await store.exists(group_key):
        await store.create(group_key, {"group_uuid": group_uuid, "created_at": now_iso()}, overwrite=True)

    ensure_group_dirs(group_uuid)
    raw_dir = group_dir_raw(group_uuid)

    created: List[FileOut] = []
    created_ids: List[str] = []

    for uf in files:
        filename = (uf.filename or "").strip()
        if not filename:
            continue
        if not _should_accept(filename):
            # пропускаем неразрешённые расширения/маковский мусор
            continue

        # путь назначения
        dst_path = raw_dir / filename
        await _save_upload_to_path(dst_path, uf)

        # метаданные файла
        fid = _fid()
        meta = {
            "file_uuid": fid,
            "group_uuid": group_uuid,
            "original_name": filename,
            "raw_path": str(dst_path),
            "status": FileStatus.progress.value,
            "created_at": now_iso(),
        }

        # statuses/{fid}.json + store/files/{fid}.json
        await atomic_write_json(group_dir_status(group_uuid) / f"{fid}.json", meta)
        await store.create(f"files/{fid}", meta, overwrite=True)
            
        created.append(FileOut(
            file_uuid=fid, group_uuid=group_uuid, filename=filename, status=FileStatus.progress
        ))
        created_ids.append(fid)
        start_ml_pipeline.send(group_uuid)
    if not created:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "no valid files to upload")

    await _append_group_index(group_uuid, created_ids)
    return created


# -------- 2) Создать новую группу и закачать файлы --------

@groups_router.post("/upload-files", response_model=GroupOut, status_code=http.HTTP_201_CREATED)
async def create_group_and_upload_files(
    files: List[UploadFile] = FAFile(..., description="Один или несколько файлов"),
    fond: Optional[str] = Form(None),
    opis: Optional[str] = Form(None),
    delo: Optional[str] = Form(None),
):
    group_uuid = _gid()
    ensure_group_dirs(group_uuid)

    group_doc = {
        "group_uuid": group_uuid,
        "fond": fond, "opis": opis, "delo": delo,
        "created_at": now_iso(),
    }
    await store.create(f"groups/{group_uuid}", group_doc, overwrite=True)

    # переиспользуем логику сохранения
    outs = await upload_files_to_group(group_uuid, files)  # type: ignore[arg-type]

    # вернём только группу; файлы фронт может прочитать через GET /groups/{gid}/files
    return GroupOut(group_uuid=group_uuid, fond=fond, opis=opis, delo=delo)

@groups_router.get("/{group_uuid}/report")
async def build_group_report(
    group_uuid: str,
    format: Format = Query("xlsx", description="Формат файла отчёта"),
    stage: Stage   = Query("progress", description="Стадия обработки: progress|done"),
    # можно передавать повторяемыми параметрами (?fields=a&fields=b) или через запятую (?fields=a,b)
    fields: Optional[List[str]] = Query(
        None,
        description="Список полей отчёта в нужном порядке: "
                    "scan_no,fond,opis,delo,text,entity_type,entity_value,extra",
    ),
    entity_types_order: Optional[List[str]] = Query(
        None,
        description="Желаемый порядок типов сущностей (repeatable или через запятую)",
    ),
    entity_joiner: str = Query("\n", description="Разделитель значений внутри одного типа"),
    deduplicate_values: bool = Query(
        True, description="Убирать повторы значений внутри одного типа"
    ),
):
    # Нормализация: поддерживаем и повторяемые query, и comma-separated
    def _normalize_list(v: Optional[List[str]]) -> Optional[List[str]]:
        if not v:
            return None
        out: List[str] = []
        for item in v:
            out.extend([s.strip() for s in item.split(",") if s.strip()])
        return out or None

    norm_fields = _normalize_list(fields)
    norm_order  = _normalize_list(entity_types_order)

    use_case = ReportBuilder()
    return await use_case(
        group_uuid=group_uuid,
        format=format,
        stage=stage,
        fields=norm_fields,
        entity_types_order=norm_order,
        entity_joiner=entity_joiner,
        deduplicate_values=deduplicate_values,
    )
