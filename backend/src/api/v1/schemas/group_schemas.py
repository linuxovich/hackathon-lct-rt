from typing import Optional

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    fond: Optional[str] = None
    opis: Optional[str] = None
    delo: Optional[str] = None

class GroupOut(GroupCreate):
    group_uuid: str

class GroupPatch(BaseModel):
    fond: Optional[str] = None
    opis: Optional[str] = None
    delo: Optional[str] = None
