"""Pydantic models for API requests (responses are rich, dynamic dicts)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="default", max_length=100)


class SeedRequest(BaseModel):
    reset: bool = True


class MemoryRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    target_id: str | None = None
    session_id: str = "default"
