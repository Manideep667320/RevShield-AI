"""
Integration tests: simulate endpoint → full pipeline → DB record verified.
Tests the HTTP API layer with in-memory DB and mocked Redis.
"""
import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.core.config import settings
from app.main import app
from app.models.customer import Customer
from app.models.merchant import Merchant


@pytest_asyncio.fixture
async def seed_merchant_customer(db):
    merchant = Merchant(merchant_id=uuid4(), name="Integration Test Merchant")
    db.add(merchant)
    customer = Customer(
        customer_id=uuid4(), merchant_id=merchant.merchant_id,
        historical_payment_count=5, successful_payment_count=4,
        risk_score=0.2,
    )
    db.add(customer)
    await db.flush()
    return merchant, customer


@pytest_asyncio.fixture
async def client(db):
    """ASGI test client with DB and Redis mocked."""
    def _override_db():
        yield db

    from app.core.database import get_db
    app.dependency_overrides[get_db] = _override_db

    publisher = AsyncMock()
    publisher.publish_payment_event = AsyncMock(return_value="stream-id-001")
    publisher.ensure_consumer_group = AsyncMock()

    with patch("app.services.payment_event.get_publisher", return_value=publisher), \
         patch("app.services.event_queue.get_publisher", return_value=publisher):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()


class TestSimulateEndpoint:

    @pytest.mark.asyncio
    async def test_simulate_payment_failure(self, client, seed_merchant_customer):
        merchant, customer = seed_merchant_customer
        response = await client.post("/api/v1/simulate/payment-failure", json={
            "merchant_id": str(merchant.merchant_id),
            "customer_id": str(customer.customer_id),
            "amount": "1500.00",
            "failure_code": "GATEWAY_ERROR",
            "payment_method": "CARD",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["failure_category"] == "TEMPORARY_FAILURE"
        assert data["queued"] is True

    @pytest.mark.asyncio
    async def test_simulate_batch(self, client):
        response = await client.post(
            "/api/v1/simulate/batch?count=3&failure_code=SERVER_ERROR"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["injected"] == 3
        assert len(data["events"]) == 3

    @pytest.mark.asyncio
    async def test_simulate_batch_limit_enforced(self, client):
        response = await client.post("/api/v1/simulate/batch?count=200")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestWebhookEndpoint:

    def _sign(self, body: bytes) -> str:
        return hmac.new(
            settings.razorpay_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature_rejected(self, client):
        body = json.dumps({"event": "payment.failed"}).encode()
        response = await client.post(
            "/api/v1/webhooks/razorpay/payment",
            content=body,
            headers={"X-Razorpay-Signature": "invalid_signature", "Content-Type": "application/json"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_webhook_valid_payment_accepted(self, client):
        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_{uuid4().hex[:16]}",
                        "amount": 50000,
                        "currency": "INR",
                        "method": "card",
                        "status": "failed",
                        "error_code": "GATEWAY_ERROR",
                        "merchant_id": str(uuid4()),
                        "customer_id": str(uuid4()),
                    }
                }
            }
        }
        body = json.dumps(payload).encode()
        response = await client.post(
            "/api/v1/webhooks/razorpay/payment",
            content=body,
            headers={
                "X-Razorpay-Signature": self._sign(body),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_webhook_empty_payload_skipped(self, client):
        payload = {"event": "order.paid", "payload": {}}
        body = json.dumps(payload).encode()
        response = await client.post(
            "/api/v1/webhooks/razorpay/payment",
            content=body,
            headers={
                "X-Razorpay-Signature": self._sign(body),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "skipped"
