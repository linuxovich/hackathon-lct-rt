from __future__ import annotations

import os
import json
import asyncio
from pathlib import Path
import mimetypes
from typing import List, Optional, Literal

from loguru import logger
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi import status as http

from src.api.v1.schemas.file_schemas import (
    FileOut, FileStatus, FilePatch, FileContentIn, FileContentOut
)
from src.utils.common import (
    stage_dir, group_dir_status, atomic_write_json, read_json_file, group_dir_final, group_dir_process
)

from src.utils.files import  _find_source_image, _copy2, _write_text_atomic

from src.infra.storage.local_storage import AsyncLocalJsonFileStoreAiofiles, JsonFileStoreConfig
from src.core.configs import configs
from src.services.report.report import FileReportBuilder

store = AsyncLocalJsonFileStoreAiofiles(JsonFileStoreConfig(base_dir=configs.dirs.store))

files_router = APIRouter(prefix="/files", tags=["files"])

Format = Literal["xlsx", "csv"]
Stage  = Literal["progress", "done"]


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
    logger.info("multiple candidate content files found")
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
    filename: str | None = Query(
        None,
        description="Имя json-файла для записи в каталоге stage. "
                    "Также используется как базовое имя для пары train JSON+image."
    ),
):
    """
    1) Сохраняем контент файла в соответствующий stage-каталог (как и раньше).
    2) Дополнительно кладём train-артефакты:
       - var/train/jsons/<basename>.json (payload как есть)
       - var/train/images/<basename>.<ext> (копия исходного изображения)
    basename = stem(filename) | stem(meta.filename/original_name) | file_uuid
    """

    # ---- 0. читаем метаданные файла (нужны имя и group_uuid) ----
    if not await store.exists(f"files/{file_uuid}"):
        raise HTTPException(status_code=http.HTTP_404_NOT_FOUND, detail="file not found")

    meta = await store.read(f"files/{file_uuid}")
    group_uuid = meta.get("group_uuid")
    original_name = (meta.get("filename") or meta.get("original_name") or "").strip()

    # ---- 1. обычная логика записи в stage-каталог (как у вас) ----
    # определяем имя JSON внутри каталога stage
    stage_dir = (group_dir_final(group_uuid) if stage == "done"
                 else group_dir_process(group_uuid))
    stage_dir.mkdir(parents=True, exist_ok=True)

    stage_json_name = filename or (Path(original_name).with_suffix(".json").name if original_name else f"{file_uuid}.json")
    stage_json_path = stage_dir / stage_json_name

    # сериализуем payload (Pydantic) в JSON
    # Если у FileContentIn нет model_dump(), замените на payload.dict()
    try:
        payload_dict = payload.model_dump()   # Pydantic v2
    except AttributeError:
        payload_dict = payload.dict()         # Pydantic v1

    # await _write_text_atomic(stage_json_path, json.dumps(payload_dict, ensure_ascii=False, indent=2))
    p = await _resolve_content_path(file_uuid, stage=stage, filename=filename, must_exist=False)
    await atomic_write_json(p, payload.json)

    # ---- 2. подготовка train-имён (единый basename для пары JSON+image) ----
    if filename:
        base_stem = Path(filename).stem
    elif original_name:
        base_stem = Path(original_name).stem
    else:
        base_stem = file_uuid

    train_root = Path("var") / "train"
    train_jsons_dir = train_root / "texts"
    train_images_dir = train_root / "images"

    train_json_path = train_jsons_dir / f"{base_stem}.json"

    # пишем train JSON такой же структурой, как пришёл payload
    await _write_text_atomic(train_json_path, json.dumps(payload_dict, ensure_ascii=False, indent=2))

    # ---- 3. ищем и копируем исходное изображение в train/images/<basename>.<ext> ----
    src_image = await _find_source_image(meta, base_stem, group_uuid)
    if src_image is None:
        # Ничего не падаем — просто сообщаем 404 по изображению в поле ответа.
        logger.info("src image is None")
        copied_image = None
    else:
        dst_image = train_images_dir / f"{base_stem}{src_image.suffix.lower()}"
        await _copy2(src_image, dst_image)
        copied_image = str(dst_image)

    return FileContentOut(
        file_uuid=file_uuid,
        json=payload.json
    )


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

@files_router.get("/{file_uuid}/report")
async def build_file_report(
    file_uuid: str,
    format: Format = Query("xlsx", description="Формат файла отчёта"),
    stage: Stage   = Query("progress", description="Стадия обработки: progress|done"),
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
    # Нормализация repeatable/comma-separated
    def _normalize_list(v: Optional[List[str]]) -> Optional[List[str]]:
        if not v:
            return None
        out: List[str] = []
        for item in v:
            out.extend([s.strip() for s in item.split(",") if s.strip()])
        return out or None

    norm_fields = _normalize_list(fields)
    norm_order  = _normalize_list(entity_types_order)

    use_case = FileReportBuilder()
    return await use_case(
        file_uuid=file_uuid,
        format=format,
        stage=stage,
        fields=norm_fields,
        entity_types_order=norm_order,
        entity_joiner=entity_joiner,
        deduplicate_values=deduplicate_values,
    )

