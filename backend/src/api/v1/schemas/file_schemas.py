import enum
from typing import Any

from pydantic import BaseModel, Field

class FileStatus(str, enum.Enum):
    progress = "progress"
    upgrading = "upgrading"
    done = "done"

class FileStatusModel(BaseModel):
    status: FileStatus 

class FileOut(BaseModel):
    file_uuid: str
    group_uuid: str
    filename: str
    status: FileStatus

class FilePatch(BaseModel):
    status: FileStatus

class FileContentOut(BaseModel):
    file_uuid: str
    json: Any = Field(default_factory=dict)

class FileContentIn(BaseModel):
    json: Any
