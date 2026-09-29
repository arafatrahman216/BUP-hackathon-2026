import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

from fastapi import Query

from app.schemas.common import Page

T = TypeVar("T")


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100),
) -> PageParams:
    """FastAPI dependency: `params: PageParams = Depends(page_params)`."""
    return PageParams(page=page, page_size=page_size)


def build_page(items: Sequence[T], total: int, params: PageParams) -> Page[T]:
    return Page[T](
        items=list(items),
        total=total,
        page=params.page,
        page_size=params.page_size,
        pages=math.ceil(total / params.page_size) if total else 0,
    )
