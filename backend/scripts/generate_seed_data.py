"""
Synthetic Seed Data Generator — Phase 1
Generates realistic merchants, customers, and failed payment events
against the real DB schema. Run after alembic upgrade head.

Usage:
    python -m scripts.generate_seed_data --merchants 5 --customers 200 --events 1000
"""
import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger
from app.models.customer import Customer
from app.models.merchant import Merchant
from app.models.payment_event import PaymentEvent
from app.services.taxonomy import classify_failure_code

logger = get_logger(__name__)

# ── Realistic synthetic data pools ────────────────────────────────────────

MERCHANT_NAMES = [
    "Zephyr Commerce", "Indigo Retail", "Apex Marketplace",
    "Sunrise Subscriptions", "NexGen Payments",
]

FAILURE_CODES = [
    ("GATEWAY_ERROR", 0.25),
    ("SERVER_ERROR", 0.10),
    ("BAD_REQUEST_ERROR:INSUFFICIENT_BALANCE", 0.20),
    ("BAD_REQUEST_ERROR:CARD_EXPIRED", 0.12),
    ("BAD_REQUEST_ERROR:PAYMENT_CANCELLED", 0.10),
    ("BAD_REQUEST_ERROR:RISK_THRESHOLD", 0.05),
    ("BAD_REQUEST_ERROR:ISSUER_NOT_AVAILABLE", 0.10),
    ("BAD_REQUEST_ERROR:INVALID_CARD", 0.08),
]

PAYMENT_METHODS = ["CARD", "UPI", "NETBANKING", "WALLET"]
CURRENCIES = ["INR"]

# Amount distribution: most transactions are small, some are large
AMOUNT_RANGES = [
    (Decimal("100"), Decimal("999"), 0.40),
    (Decimal("1000"), Decimal("9999"), 0.35),
    (Decimal("10000"), Decimal("49999"), 0.20),
    (Decimal("50000"), Decimal("200000"), 0.05),
]


def _weighted_choice(weighted_items: list[tuple]) -> str:
    items, weights = zip(*weighted_items)
    return random.choices(items, weights=weights, k=1)[0]


def _random_amount() -> Decimal:
    lo, hi, _ = random.choices(
        AMOUNT_RANGES, weights=[r[2] for r in AMOUNT_RANGES], k=1
    )[0]
    return Decimal(str(round(random.uniform(float(lo), float(hi)), 2)))


def _random_timestamp(days_back: int = 30) -> datetime:
    delta = timedelta(seconds=random.randint(0, days_back * 86400))
    return datetime.now(tz=timezone.utc) - delta


async def seed(merchants_n: int, customers_n: int, events_n: int, db_url: str | None = None) -> None:
    target_url = db_url or settings.database_url
    engine = create_async_engine(target_url, echo=False)

    if "sqlite" in target_url:
        from app.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        # ── Create Merchants ───────────────────────────────────────────────
        merchants: list[Merchant] = []
        for i in range(min(merchants_n, len(MERCHANT_NAMES))):
            m = Merchant(
                merchant_id=uuid4(),
                name=MERCHANT_NAMES[i],
                currency="INR",
                recovery_policy={"max_retry_count": 2, "approval_threshold": 25000},
            )
            db.add(m)
            merchants.append(m)
        await db.flush()
        logger.info(f"message=Merchants seeded | count={len(merchants)}")

        # ── Create Customers ───────────────────────────────────────────────
        customers: list[Customer] = []
        for _ in range(customers_n):
            hist = random.randint(1, 50)
            succ = random.randint(0, hist)
            c = Customer(
                customer_id=uuid4(),
                merchant_id=random.choice(merchants).merchant_id,
                historical_payment_count=hist,
                successful_payment_count=succ,
                average_transaction_value=_random_amount(),
                preferred_payment_methods=[random.choice(PAYMENT_METHODS)],
                last_successful_payment=_random_timestamp(90),
                risk_score=round(random.uniform(0.0, 1.0), 3),
            )
            db.add(c)
            customers.append(c)
        await db.flush()
        logger.info(f"message=Customers seeded | count={len(customers)}")

        # ── Create Payment Events ──────────────────────────────────────────
        for i in range(events_n):
            failure_code = _weighted_choice(FAILURE_CODES)
            taxonomy = classify_failure_code(failure_code)
            customer = random.choice(customers)

            event = PaymentEvent(
                event_id=uuid4(),
                merchant_id=customer.merchant_id,
                customer_id=customer.customer_id,
                payment_id=f"pay_{uuid4().hex[:16]}",
                amount=_random_amount(),
                currency="INR",
                payment_method=random.choice(PAYMENT_METHODS),
                status="failed",
                failure_code=failure_code,
                failure_category=taxonomy.internal_cause.value,
                timestamp=_random_timestamp(30),
                metadata_={"seeded": True, "seed_index": i},
            )
            db.add(event)

            if i % 100 == 0:
                await db.flush()
                logger.info(f"message=Events progress | inserted={i}/{events_n}")

        await db.commit()
        logger.info(f"message=Seed complete | merchants={len(merchants)} | customers={len(customers)} | events={events_n}")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic payment data")
    parser.add_argument("--merchants", type=int, default=5)
    parser.add_argument("--customers", type=int, default=200)
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--db-url", type=str, default=None, help="Target DB URL (overrides default)")
    args = parser.parse_args()
    asyncio.run(seed(args.merchants, args.customers, args.events, args.db_url))
