from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recommendation import Recommendation, RecommendationStatus


class RecommendationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, rec_id: int) -> Recommendation | None:
        return await self.session.get(Recommendation, rec_id)

    async def create(self, data: dict) -> Recommendation:
        rec = Recommendation(**data)
        self.session.add(rec)
        await self.session.commit()
        await self.session.refresh(rec)
        return rec

    async def update(self, rec: Recommendation, data: dict, *, commit: bool = True) -> Recommendation:
        """commit=False only flushes; the caller commits once with `commit()` (batched pipeline writes)."""
        for key, value in data.items():
            setattr(rec, key, value)
        if commit:
            await self.session.commit()
            await self.session.refresh(rec)
        else:
            await self.session.flush()
        return rec

    async def add_many(self, rows: list[dict]) -> list[Recommendation]:
        """Flush only (ids are assigned); the caller commits."""
        recs = [Recommendation(**row) for row in rows]
        self.session.add_all(recs)
        await self.session.flush()
        return recs

    async def commit(self) -> None:
        await self.session.commit()

    async def list_open(self) -> list[Recommendation]:
        rows = await self.session.scalars(
            select(Recommendation)
            .where(Recommendation.status.in_(RecommendationStatus.OPEN))
            .order_by(Recommendation.id)
            .execution_options(populate_existing=True)
        )
        return list(rows)

    async def posted_between(self, first_tick: int, last_tick: int) -> list[Recommendation]:
        rows = await self.session.scalars(
            select(Recommendation)
            .where(Recommendation.status == RecommendationStatus.POSTED,
                   Recommendation.posted_tick.between(first_tick, last_tick))
        )
        return list(rows)

    async def recent(self, limit: int) -> list[Recommendation]:
        rows = await self.session.scalars(select(Recommendation).order_by(Recommendation.id.desc()).limit(limit).execution_options(populate_existing=True))
        return list(rows)

    async def list(self, offset: int, limit: int, status: str | None = None) -> tuple[list[Recommendation], int]:
        query = select(Recommendation)
        count = select(func.count()).select_from(Recommendation)
        if status:
            query = query.where(Recommendation.status == status)
            count = count.where(Recommendation.status == status)
        total = await self.session.scalar(count)
        rows = await self.session.scalars(query.order_by(Recommendation.id.desc()).offset(offset).limit(limit))
        return list(rows), total or 0
