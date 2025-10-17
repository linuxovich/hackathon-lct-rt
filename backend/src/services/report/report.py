import http
from http.client import HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO, StringIO
import csv, json, asyncio, os, re
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional

from openpyxl import Workbook  

from src.utils.common import group_dir_process, group_dir_final
from src.core.configs import configs
from src.infra.storage.local_storage import AsyncLocalJsonFileStoreAiofiles, JsonFileStoreConfig

from collections import OrderedDict

store = AsyncLocalJsonFileStoreAiofiles(JsonFileStoreConfig(base_dir=configs.dirs.store))

_norm_result_suffix = re.compile(r"(?:_result)?$", re.IGNORECASE)
_norm_idx_suffix    = re.compile(r"_(\d{3,})$")

FIELD_LABELS = {
    "scan_no": "№ скана",
    "fond": "Фонд",
    "opis": "Опись",
    "delo": "Дело",
    "text": "Расшифрованный текст",
    "entity_type": "Тип предопределенный атрибут",
    "entity_value": "Предопределенный атрибут",
    "extra": "Дополнительная информация",
}

def _group_entities(
    ents: list[dict],
    *,
    order: list[str] | None = None,
    deduplicate: bool = True,
) -> "OrderedDict[str, list[str]]":
    """
    Группирует сущности по типу, сохраняет порядок появления.
    order — желаемый порядок типов (неуказанные типы идут в конце).
    deduplicate — убирать повторы значений внутри одного типа.
    """
    grouped: "OrderedDict[str, list[str]]" = OrderedDict()
    for e in ents or []:
        etype, eval_ = _norm_entity(e)
        etype = etype.strip()
        eval_ = eval_.strip()
        if not etype and not eval_:
            continue
        if etype not in grouped:
            grouped[etype] = []
        grouped[etype].append(eval_)

    # удаляем дубли, сохраняя порядок
    if deduplicate:
        for t, vals in grouped.items():
            seen = set()
            unique = []
            for v in vals:
                if v not in seen:
                    seen.add(v)
                    unique.append(v)
            grouped[t] = unique

    if order:
        ordered = OrderedDict()
        for t in order:
            if t in grouped:
                ordered[t] = grouped[t]
        for t, vals in grouped.items():
            if t not in ordered:
                ordered[t] = vals
        grouped = ordered

    return grouped


def _stem_norm(name: str) -> str:
    """Приводим имена вида '..._000_result.json' к базовому стему исходника."""
    stem = Path(name).stem                  # ..._000_result
    stem = _norm_result_suffix.sub("", stem)
    stem = _norm_idx_suffix.sub("", stem)
    return stem.casefold()

async def _read_json_path(p: Path) -> Dict[str, Any]:
    def _read_sync():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return await asyncio.to_thread(_read_sync)

def _pick_entities(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Универсально достаем named_entities. Ожидаем список словарей.
    Поддерживаем ключи: type / label / kind; value / text / name.
    """
    ents = data.get("named_entities") or []
    out: List[Dict[str, str]] = []
    for e in ents:
        if not isinstance(e, dict):
            continue
        etype = e.get("type") or e.get("label") or e.get("kind") or ""
        eval_ = e.get("value") or e.get("text") or e.get("name") or ""
        if etype or eval_:
            out.append({"type": str(etype), "value": str(eval_)})
    return out

def _pick_corrected_text(data: Dict[str, Any]) -> str:
    return str(data.get("corrected_text") or data.get("text") or "")

def _process_dir(group_uuid: str, stage: str) -> Path:
    return group_dir_final(group_uuid) if stage == "done" else group_dir_process(group_uuid)

def _norm_entity(e: dict) -> tuple[str, str]:
    """Поддерживаем разные названия ключей в сущности."""
    etype = (
        e.get("type") or e.get("label") or e.get("kind") or
        e.get("entity_type") or ""
    )
    eval_ = (
        e.get("value") or e.get("text") or e.get("name") or
        e.get("entity_value") or ""
    )
    return str(etype), str(eval_)

def _iter_text_and_ents(payload: dict) -> list[tuple[str, list[dict]]]:
    """
    Возвращает [(text, ents), ...].
    Если в JSON есть regions[], идём по ним; иначе читаем верхний уровень.
    """
    if isinstance(payload, dict) and "regions" in payload:
        out = []
        for reg in payload.get("regions", []):
            text = (reg.get("corrected_text")
                    or reg.get("concatenated_text")
                    or "").strip()
            ents = reg.get("named_entities") or []
            if text or ents:
                out.append((text, ents))
        return out
    return [(_pick_corrected_text(payload).strip(),
             payload.get("named_entities") or [])]


class ReportBuilder:
    async def __call__(
        self,
        group_uuid,
        format,
        stage,
        *,
        # ↓ можно пробрасывать из query: ?fields=scan_no,text,entity_type,entity_value
        fields: Optional[List[str]] = None,
        entity_types_order: Optional[List[str]] = None,  # ?entity_types_order=person,place,date
        entity_joiner: str = "\n",                      # ?entity_joiner=%0A
        deduplicate_values: bool = True,               # ?deduplicate_values=false
    ):
        # 1) метаданные группы
        gkey = f"groups/{group_uuid}"
        if not await store.exists(gkey):
            raise HTTPException(http.HTTP_404_NOT_FOUND, "group not found")
        grp = await store.read(gkey)
        fond = grp.get("fond") or ""
        opis = grp.get("opis") or ""
        delo = grp.get("delo") or ""

        # 2) список файлов группы (для номеров сканов и имён)
        file_ids: List[str] = []
        idx_key = f"group_index/{group_uuid}"
        if await store.exists(idx_key):
            idx = await store.read(idx_key)
            file_ids = list(idx.get("files", []))
        else:
            for key in await store.list("files"):
                rec = await store.read(key)
                if rec.get("group_uuid") == group_uuid:
                    file_ids.append(rec["file_uuid"])

        metas: List[Dict[str, Any]] = []
        for fid in file_ids:
            m = await store.read(f"files/{fid}")
            m.setdefault("file_uuid", fid)
            metas.append(m)
        metas.sort(key=lambda m: (m.get("filename") or m.get("original_name") or "").lower())

        # 3) stage-директория
        stage_dir = _process_dir(group_uuid, stage)
        if not stage_dir.exists():
            stage_dir.mkdir(parents=True, exist_ok=True)

        # 4) индексируем json по нормализованному стему
        json_by_stem: Dict[str, Path] = {}
        for p in stage_dir.glob("*.json"):
            if p.is_file():
                json_by_stem[_stem_norm(p.name)] = p

        # 5) какие поля выводим и в каком порядке
        default_fields = [
            "scan_no", "fond", "opis", "delo",
            "text", "entity_type", "entity_value", "extra",
        ]
        selected_fields = fields or default_fields
        # защита от опечаток
        selected_fields = [f for f in selected_fields if f in FIELD_LABELS]

        header = [FIELD_LABELS[f] for f in selected_fields]
        rows: List[List[str]] = []

        # 6) собираем строки
        for idx, meta in enumerate(metas, start=1):
            fname = (meta.get("filename") or meta.get("original_name") or "").strip()
            base_stem = _stem_norm(fname)
            payload_path = json_by_stem.get(base_stem)

            # нет результата — одна (пустая) строка
            if payload_path is None:
                row_map = {
                    "scan_no": str(idx), "fond": str(fond), "opis": str(opis),
                    "delo": str(delo), "text": "", "entity_type": "",
                    "entity_value": "", "extra": "",
                }
                rows.append([row_map.get(f, "") for f in selected_fields])
                continue

            data = await _read_json_path(payload_path)

            # идём по регионам или верхнему уровню
            for text, ents in _iter_text_and_ents(data):
                # сгруппировать сущности по типу; если их нет — одна строка без NER
                grouped = _group_entities(
                    ents,
                    order=entity_types_order,
                    deduplicate=deduplicate_values,
                )

                if not grouped:
                    row_map = {
                        "scan_no": str(idx), "fond": str(fond), "opis": str(opis),
                        "delo": str(delo), "text": text, "entity_type": "",
                        "entity_value": "", "extra": "",
                    }
                    rows.append([row_map.get(f, "") for f in selected_fields])
                    continue

                # разные типы — разные строки; значения одного типа склеиваем в «блок»
                for etype, values in grouped.items():
                    block = entity_joiner.join(v for v in values if v is not None)
                    row_map = {
                        "scan_no": str(idx), "fond": str(fond), "opis": str(opis),
                        "delo": str(delo), "text": text,
                        "entity_type": etype, "entity_value": block,
                        "extra": "",
                    }
                    rows.append([row_map.get(f, "") for f in selected_fields])

        # 7) отдаём файл
        if format.lower() == "csv":
            sio = StringIO()
            w = csv.writer(sio, delimiter=",")
            w.writerow(header)
            w.writerows(rows)
            sio.seek(0)
            filename = f"report_{group_uuid}_{stage}.csv"
            return StreamingResponse(
                iter([sio.getvalue().encode("utf-8")]),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )

        wb = Workbook()
        ws = wb.active
        ws.title = "Report"
        ws.append(header)
        for r in rows:
            ws.append(r)
        bio = BytesIO()
        wb.save(bio); bio.seek(0)
        filename = f"report_{group_uuid}_{stage}.xlsx"
        return StreamingResponse(
            bio,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )


class FileReportBuilder:
    async def __call__(
        self,
        file_uuid: str,
        format: str,
        stage: str,
        *,
        fields: Optional[List[str]] = None,
        entity_types_order: Optional[List[str]] = None,
        entity_joiner: str = "\n",
        deduplicate_values: bool = True,
    ):
        # 1) мета файла
        fkey = f"files/{file_uuid}"
        if not await store.exists(fkey):
            raise HTTPException(http.HTTP_404_NOT_FOUND, "file not found")
        fmeta = await store.read(fkey)

        group_uuid = fmeta.get("group_uuid")
        if not group_uuid:
            raise HTTPException(http.HTTP_400_BAD_REQUEST, "file has no group_uuid")

        # 2) метаданные группы (fond/opis/delo)
        gkey = f"groups/{group_uuid}"
        fond = opis = delo = ""
        if await store.exists(gkey):
            grp = await store.read(gkey)
            fond = grp.get("fond") or ""
            opis = grp.get("opis") or ""
            delo = grp.get("delo") or ""

        # 3) вычислим scan_no так же, как в групповом отчёте
        file_ids: List[str] = []
        idx_key = f"group_index/{group_uuid}"
        if await store.exists(idx_key):
            idx = await store.read(idx_key)
            file_ids = list(idx.get("files", []))
        else:
            for key in await store.list("files"):
                rec = await store.read(key)
                if rec.get("group_uuid") == group_uuid:
                    file_ids.append(rec["file_uuid"])

        metas: List[Dict[str, Any]] = []
        for fid in file_ids:
            m = await store.read(f"files/{fid}")
            m.setdefault("file_uuid", fid)
            metas.append(m)
        metas.sort(key=lambda m: (m.get("filename") or m.get("original_name") or "").lower())

        # позиция текущего файла в отсортированном списке (как в групповом отчёте)
        scan_no = ""
        for idx, m in enumerate(metas, start=1):
            if m.get("file_uuid") == file_uuid:
                scan_no = str(idx)
                break

        # 4) stage-директория и поиск JSON по стему файла
        stage_dir = _process_dir(group_uuid, stage)
        if not stage_dir.exists():
            stage_dir.mkdir(parents=True, exist_ok=True)

        json_by_stem: Dict[str, Path] = {}
        for p in stage_dir.glob("*.json"):
            if p.is_file():
                json_by_stem[_stem_norm(p.name)] = p

        fname = (fmeta.get("filename") or fmeta.get("original_name") or "").strip()
        base_stem = _stem_norm(fname)
        payload_path = json_by_stem.get(base_stem)

        # 5) поля/заголовки
        default_fields = [
            "scan_no", "fond", "opis", "delo",
            "text", "entity_type", "entity_value", "extra",
        ]
        selected_fields = [f for f in (fields or default_fields) if f in FIELD_LABELS]
        header = [FIELD_LABELS[f] for f in selected_fields]
        rows: List[List[str]] = []

        # 6) собрать строки
        if payload_path is None:
            # нет результата — одна пустая строка
            row_map = {
                "scan_no": scan_no, "fond": str(fond), "opis": str(opis), "delo": str(delo),
                "text": "", "entity_type": "", "entity_value": "", "extra": "",
            }
            rows.append([row_map.get(f, "") for f in selected_fields])
        else:
            data = await _read_json_path(payload_path)
            for text, ents in _iter_text_and_ents(data):
                grouped = _group_entities(
                    ents,
                    order=entity_types_order,
                    deduplicate=deduplicate_values,
                )
                if not grouped:
                    row_map = {
                        "scan_no": scan_no, "fond": str(fond), "opis": str(opis), "delo": str(delo),
                        "text": text, "entity_type": "", "entity_value": "", "extra": "",
                    }
                    rows.append([row_map.get(f, "") for f in selected_fields])
                    continue

                for etype, values in grouped.items():
                    block = entity_joiner.join(v for v in values if v is not None)
                    row_map = {
                        "scan_no": scan_no, "fond": str(fond), "opis": str(opis), "delo": str(delo),
                        "text": text, "entity_type": etype, "entity_value": block, "extra": "",
                    }
                    rows.append([row_map.get(f, "") for f in selected_fields])

        # 7) отдать файл (CSV/XLSX) — полностью аналогично групповому отчёту
        if format.lower() == "csv":
            sio = StringIO()
            w = csv.writer(sio, delimiter=",")
            w.writerow(header)
            w.writerows(rows)
            sio.seek(0)
            filename = f"report_file_{file_uuid}_{stage}.csv"
            return StreamingResponse(
                iter([sio.getvalue().encode("utf-8")]),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )

        wb = Workbook()
        ws = wb.active
        ws.title = "Report"
        ws.append(header)
        for r in rows:
            ws.append(r)
        bio = BytesIO()
        wb.save(bio); bio.seek(0)
        filename = f"report_file_{file_uuid}_{stage}.xlsx"
        return StreamingResponse(
            bio,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

