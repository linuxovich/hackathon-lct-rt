from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

class JobStatus(enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"

@dataclass(frozen=True)
class JobId:
    value: str

@dataclass(frozen=True)
class JobMeta:
    id: JobId
    status: JobStatus
    submitted_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    # Папка для результатов
    output_dir: Path = Path(".")
    # Произвольные пользовательские метаданные
    user_meta: dict = field(default_factory=dict)
    # Сообщение об ошибке, если есть
    error: Optional[str] = None

@dataclass(frozen=True)
class SubmitOptions:
    output_dir: Path
    # Если нужно, можно заранее задать имя базового файла результата (без расширения)
    output_basename: Optional[str] = None
    user_meta: dict = field(default_factory=dict)

# ---------- Интерфейс процессора ----------

class AsyncImageProcessor(abc.ABC):
    """
    Единый контракт для любых обработчиков (локальный процесс, REST/gRPC, очередь).
    Обработчик принимает путь к изображению (или директории) и пишет результаты в output_dir.
    """

    @abc.abstractmethod
    async def submit(self, input_path: Path, options: SubmitOptions) -> JobMeta:
        """Поставить задачу. Возвращает метаданные новой задачи."""

    @abc.abstractmethod
    async def get(self, job_id: JobId) -> JobMeta:
        """Получить текущее состояние задачи."""

    @abc.abstractmethod
    async def cancel(self, job_id: JobId) -> None:
        """Отменить задачу (best-effort)."""

    @abc.abstractmethod
    async def wait(self, job_id: JobId, *, timeout: Optional[float] = None) -> JobMeta:
        """Дождаться завершения (SUCCEEDED/FAILED/CANCELED) или таймаута."""

    @abc.abstractmethod
    async def stream_logs(self, job_id: JobId) -> AsyncIterator[str]:
        """Асинхронный стрим логов задачи (если есть)."""

