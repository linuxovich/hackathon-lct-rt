from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Iterable, Optional, Union


Json = Any
PatchFn = Union[Callable[[Json], Json], Callable[[Json], Awaitable[Json]]]


class AsyncFileStorageI(ABC):
    """Асинхронный интерфейс JSON-хранилища."""

    @abstractmethod
    async def create(self, key: str, data: Json, *, overwrite: bool = False) -> None: ...
    @abstractmethod
    async def read(self, key: str) -> Json: ...
    @abstractmethod
    async def replace(
        self, key: str, data: Json, *, if_match_mtime: Optional[float] = None
    ) -> float: ...
    @abstractmethod
    async def update(
        self, key: str, patch: PatchFn, *, if_match_mtime: Optional[float] = None
    ) -> float: ...
    @abstractmethod
    async def delete(self, key: str, *, missing_ok: bool = False) -> None: ...
    @abstractmethod
    async def exists(self, key: str) -> bool: ...
    @abstractmethod
    async def list(self, prefix: str = "", *, recursive: bool = True) -> Iterable[str]: ...


