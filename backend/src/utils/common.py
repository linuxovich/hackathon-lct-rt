import re
import asyncio
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import List, Optional

from fastapi import UploadFile


from src.core.configs import configs

from src.infra.storage.local_storage import AsyncLocalJsonFileStoreAiofiles, JsonFileStoreConfig
from src.core.configs import configs


store = AsyncLocalJsonFileStoreAiofiles(JsonFileStoreConfig(base_dir=configs.dirs.store))

# --------- ID/время ---------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _gid() -> str: return str(uuid4())
def _fid() -> str: return str(uuid4())

# --------- Групповые директории ---------

DATA_DIR   = configs.dirs.data
GROUPS_DIR = DATA_DIR / "groups"

def group_root(group_uuid: str) -> Path:
    return (GROUPS_DIR / group_uuid).resolve()

def group_dir_raw(group_uuid: str) -> Path:
    return group_root(group_uuid) / "raw_data"

def group_dir_status(group_uuid: str) -> Path:
    return group_root(group_uuid) / "statuses"

def group_dir_process(group_uuid: str) -> Path:
    return group_root(group_uuid) / "process"

def group_dir_final(group_uuid: str) -> Path:
    return group_root(group_uuid) / "final"

def ensure_group_dirs(group_uuid: str) -> None:
    for d in (
        group_dir_raw(group_uuid),
        group_dir_status(group_uuid),
        group_dir_process(group_uuid),
        group_dir_final(group_uuid),
    ):
        d.mkdir(parents=True, exist_ok=True)

def stage_dir(group_uuid: str, stage: str) -> Path:
    return group_dir_final(group_uuid) if stage == "done" else group_dir_process(group_uuid)

# --------- macOS-мусор и фильтры ---------

def _is_trash_member(name: str) -> bool:
    base = name.rsplit("/", 1)[-1]
    return name.startswith("__MACOSX/") or base.startswith("._") or base == ".DS_Store"

def _is_allowed_ext(path: Path) -> bool:
    return path.suffix.lower() in configs.allowed_exts

# --------- IO-хелперы ---------

async def _save_upload_to_tmp(upload: UploadFile) -> Path:
    fd, tmp_name = await asyncio.to_thread(lambda: tempfile.mkstemp(prefix="upload_", suffix=".zip"))
    os.close(fd)
    try:
        with open(tmp_name, "wb") as out:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        return Path(tmp_name)
    except Exception:
        try: os.remove(tmp_name)
        except OSError: pass
        raise

async def extract_zip_filtered(zip_path: Path, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    def _extract_safe() -> List[Path]:
        files: List[Path] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for zinfo in zf.infolist():
                name = zinfo.filename
                if zinfo.is_dir() or _is_trash_member(name):
                    continue
                rel = Path(name)
                if not _is_allowed_ext(rel):
                    continue
                target = (out_dir / rel).resolve()
                if not str(target).startswith(str(out_dir.resolve()) + os.sep):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(zinfo) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                files.append(target)
        return files

    return await asyncio.to_thread(_extract_safe)

async def atomic_write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def _do():
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=path.suffix or ".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try: os.remove(tmp)
            except OSError: pass
            raise
        finally:
            try: os.close(fd)
            except OSError: pass

    await asyncio.to_thread(_do)

async def read_json_file(path: Path):
    def _read():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return await asyncio.to_thread(_read)

# --- Нормализация имён ---

_RESULT_SUFFIX = re.compile(r"(?:_result)?$", re.IGNORECASE)
_TRAIL_IDX     = re.compile(r"_(\d{3,})$")

def _normalize_to_stem(name: str) -> str:
    """
    Принимаем:
      - 'photo_2025-09-26_19-16-37_000_result.json'
    Возвращаем:
      - 'photo_2025-09-26_19-16-37'
    """
    stem = Path(name).stem                # → 'photo_..._000_result'
    stem = _RESULT_SUFFIX.sub("", stem)   # срежем '_result'
    stem = _TRAIL_IDX.sub("", stem)       # срежем '_000' (или '_0012' и т.п.)
    return stem.casefold()


async def _resolve_fid_by_filename(group_uuid: str, filename: str) -> Optional[str]:
    idx_key = f"group_index/{group_uuid}"
    target_stem = _normalize_to_stem(filename)

    if await store.exists(idx_key):
        idx = await store.read(idx_key)
        candidates = idx.get("files", [])
    else:
        candidates = []

    # Обходим все файл-меты группы
    for fid in candidates:
        meta = await store.read(f"files/{fid}")
        src_name = (meta.get("filename") or meta.get("original_name") or "").strip()
        if not src_name:
            continue
        meta_stem = _normalize_to_stem(src_name)
        # точное совпадение стемов или "результат" начинается со стема исходника
        if target_stem == meta_stem or target_stem.startswith(meta_stem) or meta_stem.startswith(target_stem):
            return fid
    return None
