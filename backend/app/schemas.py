from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .catalog import AVATAR_COLORS


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str | None
    name: str
    description: str
    tools: list[str]
    builtin: bool


class AgentTemplateOut(BaseModel):
    key: str
    title: str
    description: str
    personality: str
    instructions: str
    skill_keys: list[str]
    avatar_color: str


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str
    avatar_color: str
    personality: str
    instructions: str
    model_profile: str
    status: str
    active: bool
    retired_at: datetime | None
    template_key: str | None
    skills: list[SkillOut]
    created_at: datetime
    updated_at: datetime


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]


def _check_color(value: str | None) -> str | None:
    if value is not None and value not in AVATAR_COLORS:
        raise ValueError(f"avatar_color must be one of {AVATAR_COLORS}")
    return value


class AgentCreate(BaseModel):
    name: Name
    title: Title = ""
    avatar_color: str | None = None
    personality: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=8000)
    model_profile: str
    skill_ids: list[int] = []
    template_key: str | None = None

    _color = field_validator("avatar_color")(_check_color)


class AgentUpdate(BaseModel):
    name: Name | None = None
    title: Title | None = None
    avatar_color: str | None = None
    personality: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=8000)
    model_profile: str | None = None
    skill_ids: list[int] | None = None

    _color = field_validator("avatar_color")(_check_color)
