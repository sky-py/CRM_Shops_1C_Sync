from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from db.db_init_async import Session_async
from db.models import PromOrderDB, UkrsalonOrderDB
from sqlalchemy import select


@dataclass(slots=True)
class ClaimResult:
    status: Literal['accepted', 'already_claimed', 'not_found']
    claimed_by_name: str | None = None
    claimed_at: datetime | None = None


async def claim_ukrsalon_order(insales_id: int, manager_name: str) -> ClaimResult:
    async with Session_async.begin() as session:
        stmt = select(UkrsalonOrderDB).where(UkrsalonOrderDB.insales_id == insales_id).with_for_update()
        order_db = (await session.execute(stmt)).scalar_one_or_none()
        if order_db is None:
            return ClaimResult(status='not_found')
        if order_db.claimed_by_name:
            return ClaimResult(
                status='already_claimed', claimed_by_name=order_db.claimed_by_name, claimed_at=order_db.claimed_at
            )

        order_db.claimed_by_name = manager_name
        order_db.claimed_at = datetime.now()
        await session.flush()
        return ClaimResult(status='accepted', claimed_by_name=order_db.claimed_by_name, claimed_at=order_db.claimed_at)


async def claim_prom_order(order_id: str, shop_name: str, manager_name: str) -> ClaimResult:
    async with Session_async.begin() as session:
        stmt = (
            select(PromOrderDB)
            .where(PromOrderDB.order_id == int(order_id), PromOrderDB.shop == shop_name)
            .with_for_update()
        )
        order_db = (await session.execute(stmt)).scalar_one_or_none()
        if order_db is None:
            return ClaimResult(status='not_found')
        if order_db.claimed_by_name:
            return ClaimResult(
                status='already_claimed', claimed_by_name=order_db.claimed_by_name, claimed_at=order_db.claimed_at
            )

        order_db.claimed_by_name = manager_name
        order_db.claimed_at = datetime.now()
        await session.flush()
        return ClaimResult(status='accepted', claimed_by_name=order_db.claimed_by_name, claimed_at=order_db.claimed_at)
