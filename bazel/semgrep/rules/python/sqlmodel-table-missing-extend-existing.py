# Tests for sqlmodel-table-missing-extend-existing rule.
from typing import Optional
from sqlmodel import SQLModel, Field


# ruleid: sqlmodel-table-missing-extend-existing
class BadModelMissingExtendExisting(SQLModel, table=True):
    __table_args__ = {"schema": "myapp"}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


# ruleid: sqlmodel-table-missing-extend-existing
class BadModelWithExtraKeys(SQLModel, table=True):
    __table_args__ = {"schema": "myapp", "comment": "user records"}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


# ok: has extend_existing=True
class OkModelWithExtendExisting(SQLModel, table=True):
    __table_args__ = {"schema": "myapp", "extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


# ok: has extend_existing=True along with other keys
class OkModelWithAllKeys(SQLModel, table=True):
    __table_args__ = {
        "schema": "myapp",
        "comment": "user records",
        "extend_existing": True,
    }
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


# ok: no schema key — extend_existing not required
class OkModelNoSchema(SQLModel, table=True):
    __table_args__ = {"comment": "simple table"}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


# ok: no __table_args__ at all
class OkModelNoTableArgs(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
