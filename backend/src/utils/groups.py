from __future__ import annotations

import os
import asyncio
from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile, File as FAFile, Form, HTTPException
from fastapi import status as http

from src.api.v1.schemas.group_schemas import GroupOut
from src.api.v1.schemas.file_schemas import FileOut, FileStatus
from src.infra.storage.local_storage import AsyncLocalJsonFileStoreAiofiles, JsonFileStoreConfig
from src.core.configs import configs
from src.utils.common import (
    _gid, _fid, now_iso,
    ensure_group_dirs, group_dir_raw, group_dir_status,
    atomic_write_json, _is_allowed_ext, _is_trash_member,
)

store = AsyncLocalJsonFileStoreAiofiles(JsonFileStoreConfig(base_dir=configs.dirs.store))


async def _save_upload_to_path(dst_path: Path, uf: UploadFile) -> None:
    """Сохранить UploadFile на диск атомарно (через временный файл)."""
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    # пишем во временный рядом, затем os.replace
    import tempfile
    fd, tmp_name = await asyncio.to_thread(
        lambda: tempfile.mkstemp(dir=dst_path.parent, prefix=".up_", suffix=dst_path.suffix or "")
    )
    try:
        # потоковая запись
        with os.fdopen(fd, "wb", closefd=False) as tmp:
            while True:
                chunk = await uf.read(1 << 20)
                if not chunk:
                    break
                tmp.write(chunk)
            tmp.flush(); os.fsync(tmp.fileno())
        await asyncio.to_thread(os.replace, tmp_name, dst_path)
    except Exception:
        try: await asyncio.to_thread(os.remove, tmp_name)
        except OSError: pass
        raise
    finally:
        try: os.close(fd)
        except OSError: pass


async def _append_group_index(group_uuid: str, file_ids: List[str]) -> None:
    idx_key = f"group_index/{group_uuid}"
    if await store.exists(idx_key):
        idx = await store.read(idx_key)
        cur = set(idx.get("files", []))
        cur.update(file_ids)
        await store.create(idx_key, {"files": sorted(cur)}, overwrite=True)
    else:
        await store.create(idx_key, {"files": file_ids}, overwrite=True)


def _should_accept(filename: str) -> bool:
    if _is_trash_member(filename):
        return False
    return _is_allowed_ext(Path(filename))
