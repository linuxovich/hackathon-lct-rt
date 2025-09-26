from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Optional, Union, Dict

import aiofiles

from src.infra.storage.interface import AsyncFileStorageI 

Json = Any
PatchFn = Union[Callable[[Json], Json], Callable[[Json], Awaitable[Json]]]


@dataclass(frozen=True)
class JsonFileStoreConfig:
    base_dir: Path
    indent: int = 2
    encoding: str = "utf-8"
    suffix: str = ".json"
    max_io_concurrency: int = 64  # ограничение параллелизма


class AsyncLocalJsonFileStoreAiofiles(AsyncFileStorageI):
    """
    Реализация на локальной ФС:
    - Чтение/запись файлов через aiofiles.
    - Атомарная запись: временный файл (+ fsync) → os.replace.
    - Пер-файловые asyncio.Lock для сериализации конкурентных записей.
    - Оптимистичная блокировка по mtime (if_match_mtime).
    """

    def __init__(self, config: JsonFileStoreConfig):
        self.cfg = config
        self._base_dir: Path = self.cfg.base_dir.resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[Path, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()
        self._io_sem = asyncio.Semaphore(self.cfg.max_io_concurrency)

    # ---------- Публичные методы ----------

    async def create(self, key: str, data: Json, *, overwrite: bool = False) -> None:
        path = self._key_to_path(key)
        if not overwrite and await self._exists(path):
            raise FileExistsError(f"Key already exists: {key}")
        await self._atomic_write(path, data)

    async def read(self, key: str) -> Json:
        path = self._key_to_path(key)
        async with self._io_sem:
            async with aiofiles.open(path, "r", encoding=self.cfg.encoding) as f:
                text = await f.read()
            return json.loads(text)

    async def replace(
        self, key: str, data: Json, *, if_match_mtime: Optional[float] = None
    ) -> float:
        path = self._key_to_path(key)
        lock = await self._lock_for(path)
        async with lock:
            if if_match_mtime is not None:
                current = await self._mtime_or_none(path)
                if current is None or abs(current - if_match_mtime) > 1e-9:
                    raise FileExistsError(f"Concurrent modification detected for {key}")
            await self._atomic_write(path, data)
            return await self._mtime(path)

    async def update(
        self, key: str, patch: PatchFn, *, if_match_mtime: Optional[float] = None
    ) -> float:
        path = self._key_to_path(key)
        lock = await self._lock_for(path)
        async with lock:
            if if_match_mtime is not None:
                current = await self._mtime_or_none(path)
                if current is None or abs(current - if_match_mtime) > 1e-9:
                    raise FileExistsError(f"Concurrent modification detected for {key}")

            data = await self.read(key)
            new_data = patch(data)
            if asyncio.iscoroutine(new_data):
                new_data = await new_data
            await self._atomic_write(path, new_data)
            return await self._mtime(path)

    async def delete(self, key: str, *, missing_ok: bool = False) -> None:
        path = self._key_to_path(key)
        async with self._io_sem:
            try:
                await asyncio.to_thread(path.unlink)
            except FileNotFoundError:
                if not missing_ok:
                    raise

    async def exists(self, key: str) -> bool:
        return await self._exists(self._key_to_path(key))

    async def list(self, prefix: str = "", *, recursive: bool = True) -> Iterable[str]:
        base = (self._base_dir / prefix).resolve()
        self._ensure_within_base(base)
        if not base.exists():
            return []
        async with self._io_sem:
            def _scan():
                it = base.rglob(f"*{self.cfg.suffix}") if recursive else base.glob(f"*{self.cfg.suffix}")
                return [str(p.relative_to(self._base_dir)) for p in it if p.is_file()]
            return await asyncio.to_thread(_scan)

    # ---------- Внутреннее ----------

    def _key_to_path(self, key: str) -> Path:
        p = (self._base_dir / key).with_suffix(self.cfg.suffix)
        p = p.resolve()
        self._ensure_within_base(p)
        return p

    def _ensure_within_base(self, p: Path) -> None:
        base = self._base_dir.resolve()
        if not str(p).startswith(str(base) + os.sep) and p != base:
            raise ValueError(f"Path escapes base_dir: {p}")

    async def _lock_for(self, p: Path) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(p)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[p] = lock
            return lock

    async def _mtime(self, p: Path) -> float:
        async with self._io_sem:
            return await asyncio.to_thread(lambda: p.stat().st_mtime)

    async def _mtime_or_none(self, p: Path) -> Optional[float]:
        async with self._io_sem:
            def _stat_or_none():
                try:
                    return p.stat().st_mtime
                except FileNotFoundError:
                    return None
            return await asyncio.to_thread(_stat_or_none)

    async def _exists(self, p: Path) -> bool:
        async with self._io_sem:
            return await asyncio.to_thread(p.exists)

    async def _atomic_write(self, path: Path, data: Json) -> None:
        # Пишем JSON-текст в temp-файл в той же директории, затем fsync + os.replace
        path.parent.mkdir(parents=True, exist_ok=True)
        dir_ = path.parent

        # Создаём имя временного файла в том же каталоге (чтобы rename был атомарным)
        fd, tmp_name = await asyncio.to_thread(
            lambda: tempfile.mkstemp(dir=dir_, prefix=".tmp_", suffix=self.cfg.suffix)
        )

        try:
            # Запись через aiofiles
            async with self._io_sem:
                async with aiofiles.open(fd, "w", encoding=self.cfg.encoding, closefd=False) as tmp:
                    # json.dumps быстрее единой строкой, чем по кускам
                    text = json.dumps(data, ensure_ascii=False, indent=self.cfg.indent)
                    await tmp.write(text)
                    await tmp.flush()
                    # fsync — в отдельном потоке (не блокируем loop)
                    await asyncio.to_thread(os.fsync, tmp.fileno())

            # Атомарная замена — тоже в отдельном потоке
            await asyncio.to_thread(os.replace, tmp_name, path)
        except Exception:
            # Чистим временный файл
            try:
                await asyncio.to_thread(os.remove, tmp_name)
            except OSError:
                pass
            raise
        finally:
            # mkstemp вернул дескриптор — убедимся, что он закрыт,
            # aiofiles(closefd=False) не закрывает fd автоматически при исключениях
            try:
                os.close(fd)
            except OSError:
                pass
