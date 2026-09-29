from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.snapshot import TickSnapshot


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict) -> TickSnapshot:
        snapshot = TickSnapshot(**data)
        self.session.add(snapshot)
        await self.session.commit()  # no refresh: written every tick, rarely read back
        return snapshot

    async def list(self, offset: int, limit: int) -> tuple[list[TickSnapshot], int]:
        total = await self.session.scalar(select(func.count()).select_from(TickSnapshot))
        rows = await self.session.scalars(
            select(TickSnapshot).order_by(TickSnapshot.id.desc()).offset(offset).limit(limit)
        )
        return list(rows), total or 0
