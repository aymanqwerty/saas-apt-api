from pydantic import BaseModel


class PageMeta(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class Page[T](BaseModel):
    items: list[T]
    meta: PageMeta

    @classmethod
    def build(cls, items: list[T], total: int, page: int, limit: int) -> "Page[T]":
        total_pages = (total + limit - 1) // limit if limit else 0
        return cls(
            items=items,
            meta=PageMeta(page=page, limit=limit, total=total, total_pages=total_pages),
        )
