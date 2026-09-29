from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_question import ActionQuestion


class ActionQuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict) -> ActionQuestion:
        row = ActionQuestion(**data)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_for(self, recommendation_id: int, limit: int = 50) -> list[ActionQuestion]:
        rows = await self.session.scalars(
            select(ActionQuestion).where(ActionQuestion.recommendation_id == recommendation_id)
            .order_by(ActionQuestion.id.desc()).limit(limit)
        )
        return list(rows)
