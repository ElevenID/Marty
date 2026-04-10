"""
Billing API Routes

Backend endpoints matching the frontend paymentApi.js contract.
All endpoints are prefixed with /v1/billing.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Organization, Subscription, SubscriptionStatus
from .square_service import (
    PLAN_LIMITS,
    SquareConfig,
    SquareError,
    SquarePlan,
    SquareService,
)

logger = logging.getLogger(__name__)

billing_router = APIRouter(prefix="/v1/billing", tags=["Billing"])


# --- Pydantic schemas (match paymentApi.js request bodies) ---

class SubscribeRequest(BaseModel):
    organization_id: UUID
    plan_tier: str = Field(
        ..., description="One of: sandbox, program, institution, system"
    )
    payment_nonce: Optional[str] = None


class ChangePlanRequest(BaseModel):
    organization_id: UUID
    new_plan_tier: str


class CancelRequest(BaseModel):
    organization_id: UUID
    at_period_end: bool = True


class AddPaymentMethodRequest(BaseModel):
    organization_id: UUID
    payment_nonce: str


class SubscriptionResponse(BaseModel):
    id: str
    organization_id: str
    plan: str
    status: str
    api_calls_used: int
    api_calls_limit: int
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None
    created_at: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: str
    amount: int
    currency: str
    status: str
    created_at: str


class PaymentMethodResponse(BaseModel):
    id: str
    card_brand: Optional[str] = None
    last_4: Optional[str] = None
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None


class ErrorResponse(BaseModel):
    detail: str


# --- Tier name mapping (canonical → SquarePlan) ---

_CANONICAL_TO_SQUARE: dict[str, SquarePlan] = {
    "sandbox": SquarePlan.SANDBOX,
    "program": SquarePlan.PROGRAM,
    "institution": SquarePlan.INSTITUTION,
    "system": SquarePlan.SYSTEM,
}


def _resolve_plan(tier: str) -> SquarePlan:
    """Resolve a canonical tier name to a SquarePlan enum value."""
    plan = _CANONICAL_TO_SQUARE.get(tier)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan tier: {tier}. "
            f"Must be one of: {', '.join(_CANONICAL_TO_SQUARE)}",
        )
    return plan


# --- Dependency injection ---

_square_service_factory = None
_db_session_factory = None


def configure_billing_dependencies(
    square_service_factory,
    db_session_factory,
):
    """Configure dependency factories. Called at application startup."""
    global _square_service_factory, _db_session_factory
    _square_service_factory = square_service_factory
    _db_session_factory = db_session_factory


async def get_square_service() -> SquareService:
    if _square_service_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing service not configured",
        )
    return await _square_service_factory()


async def get_db_session() -> AsyncSession:
    if _db_session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured",
        )
    return await _db_session_factory()


# --- Route helpers ---

async def _get_org(db: AsyncSession, org_id: UUID) -> Organization:
    """Fetch org or raise 404."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )
    return org


async def _get_active_subscription(
    db: AsyncSession, org_id: UUID
) -> Subscription:
    """Fetch the active subscription for an org or raise 404."""
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.organization_id == org_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )
    return sub


def _sub_response(sub: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=str(sub.id),
        organization_id=str(sub.organization_id),
        plan=sub.plan,
        status=sub.status.value if isinstance(sub.status, SubscriptionStatus) else sub.status,
        api_calls_used=sub.api_calls_used,
        api_calls_limit=sub.api_calls_limit,
        current_period_start=(
            sub.current_period_start.isoformat() if sub.current_period_start else None
        ),
        current_period_end=(
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        created_at=sub.created_at.isoformat() if sub.created_at else None,
    )


# --- Routes ---

@billing_router.post(
    "/subscribe",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new subscription",
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def subscribe(
    body: SubscribeRequest,
    service: SquareService = Depends(get_square_service),
    db: AsyncSession = Depends(get_db_session),
):
    plan = _resolve_plan(body.plan_tier)
    org = await _get_org(db, body.organization_id)
    try:
        sub = await service.create_subscription(
            organization=org,
            plan=plan,
            card_id=body.payment_nonce,
        )
        return _sub_response(sub)
    except SquareError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@billing_router.post(
    "/change-plan",
    response_model=SubscriptionResponse,
    summary="Upgrade or downgrade the subscription plan",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def change_plan(
    body: ChangePlanRequest,
    service: SquareService = Depends(get_square_service),
    db: AsyncSession = Depends(get_db_session),
):
    new_plan = _resolve_plan(body.new_plan_tier)
    sub = await _get_active_subscription(db, body.organization_id)
    try:
        updated = await service.upgrade_subscription(sub, new_plan)
        return _sub_response(updated)
    except SquareError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@billing_router.post(
    "/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel a subscription",
    responses={404: {"model": ErrorResponse}},
)
async def cancel(
    body: CancelRequest,
    service: SquareService = Depends(get_square_service),
    db: AsyncSession = Depends(get_db_session),
):
    sub = await _get_active_subscription(db, body.organization_id)
    try:
        await service.cancel_subscription(sub, immediately=not body.at_period_end)
        return {"status": "canceled" if not body.at_period_end else "pending_cancellation"}
    except SquareError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@billing_router.get(
    "/subscription",
    response_model=SubscriptionResponse,
    summary="Get current subscription status",
    responses={404: {"model": ErrorResponse}},
)
async def get_subscription(
    organization_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
    sub = await _get_active_subscription(db, organization_id)
    return _sub_response(sub)


@billing_router.get(
    "/invoices",
    summary="Get invoice history",
)
async def get_invoices(
    organization_id: UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: SquareService = Depends(get_square_service),
    db: AsyncSession = Depends(get_db_session),
):
    org = await _get_org(db, organization_id)
    if not org.square_customer_id:
        return {"invoices": [], "total": 0}

    try:
        client = await service._get_client()
        response = await client.post(
            "/invoices/search",
            json={
                "query": {
                    "filter": {
                        "customer_ids": [org.square_customer_id],
                    },
                    "sort": {"field": "INVOICE_SORT_DATE", "order": "DESC"},
                    "limit": limit,
                },
            },
        )
        if response.status_code != 200:
            return {"invoices": [], "total": 0}

        data = response.json()
        invoices = [
            InvoiceResponse(
                id=inv.get("id", ""),
                amount=inv.get("payment_requests", [{}])[0]
                .get("computed_amount_money", {})
                .get("amount", 0),
                currency=inv.get("payment_requests", [{}])[0]
                .get("computed_amount_money", {})
                .get("currency", "USD"),
                status=inv.get("status", "UNKNOWN"),
                created_at=inv.get("created_at", ""),
            )
            for inv in data.get("invoices", [])
        ]
        return {"invoices": invoices, "total": len(invoices)}
    except Exception:
        logger.exception("Failed to fetch invoices for org %s", organization_id)
        return {"invoices": [], "total": 0}


@billing_router.post(
    "/payment-methods",
    summary="Add a payment method",
    responses={400: {"model": ErrorResponse}},
)
async def add_payment_method(
    body: AddPaymentMethodRequest,
    service: SquareService = Depends(get_square_service),
    db: AsyncSession = Depends(get_db_session),
):
    org = await _get_org(db, body.organization_id)
    if not org.square_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization has no billing account",
        )

    try:
        client = await service._get_client()
        response = await client.post(
            "/cards",
            json={
                "idempotency_key": str(body.organization_id),
                "source_id": body.payment_nonce,
                "card": {
                    "customer_id": org.square_customer_id,
                },
            },
        )
        if response.status_code != 200:
            raise SquareError(f"Failed to add card: {response.text}")

        card = response.json().get("card", {})
        return PaymentMethodResponse(
            id=card.get("id", ""),
            card_brand=card.get("card_brand"),
            last_4=card.get("last_4"),
            exp_month=card.get("exp_month"),
            exp_year=card.get("exp_year"),
        )
    except SquareError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@billing_router.get(
    "/payment-methods",
    summary="List payment methods",
)
async def get_payment_methods(
    organization_id: UUID = Query(...),
    service: SquareService = Depends(get_square_service),
    db: AsyncSession = Depends(get_db_session),
):
    org = await _get_org(db, organization_id)
    if not org.square_customer_id:
        return {"payment_methods": []}

    try:
        client = await service._get_client()
        response = await client.get(
            f"/cards?customer_id={org.square_customer_id}",
        )
        if response.status_code != 200:
            return {"payment_methods": []}

        cards = response.json().get("cards", [])
        return {
            "payment_methods": [
                PaymentMethodResponse(
                    id=c.get("id", ""),
                    card_brand=c.get("card_brand"),
                    last_4=c.get("last_4"),
                    exp_month=c.get("exp_month"),
                    exp_year=c.get("exp_year"),
                )
                for c in cards
            ]
        }
    except Exception:
        logger.exception("Failed to fetch cards for org %s", organization_id)
        return {"payment_methods": []}


# --- One-time payment processing (applicant processing fees) ---

# Separate router on /api/payments to match frontend contract.
payments_router = APIRouter(prefix="/api/payments", tags=["Payments"])


class ProcessPaymentRequest(BaseModel):
    amount_cents: int = Field(..., gt=0, le=5000, description="Amount in cents (max $50)")
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    source_id: str = Field(..., min_length=1, description="Square card nonce or token")
    # Arbitrary metadata fields are spread into the body by the frontend
    billing_contact: Optional[dict] = None
    metadata: Optional[dict] = None


class ProcessPaymentResponse(BaseModel):
    payment_id: str
    status: str
    amount_cents: int
    currency: str


@payments_router.post(
    "/process",
    response_model=ProcessPaymentResponse,
    summary="Process a one-time payment",
    description="Process a one-time card payment for applicant processing fees via Square Payments API.",
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def process_payment(
    body: ProcessPaymentRequest,
    service: SquareService = Depends(get_square_service),
):
    try:
        client = await service._get_client()
        import uuid as _uuid

        idempotency_key = str(_uuid.uuid4())

        square_body: dict = {
            "idempotency_key": idempotency_key,
            "amount_money": {
                "amount": body.amount_cents,
                "currency": body.currency,
            },
            "source_id": body.source_id,
        }

        # Attach optional metadata as a note (Square doesn't have a metadata field)
        if body.metadata:
            note_parts = [f"{k}={v}" for k, v in body.metadata.items() if v]
            if note_parts:
                square_body["note"] = "; ".join(note_parts)[:500]

        response = await client.post("/payments", json=square_body)

        if response.status_code != 200:
            error_detail = "Payment processing failed"
            try:
                err_data = response.json()
                errors = err_data.get("errors", [])
                if errors:
                    error_detail = errors[0].get("detail", error_detail)
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail,
            )

        data = response.json()
        payment = data.get("payment", {})

        return ProcessPaymentResponse(
            payment_id=payment.get("id", ""),
            status=payment.get("status", "UNKNOWN"),
            amount_cents=payment.get("amount_money", {}).get("amount", body.amount_cents),
            currency=payment.get("amount_money", {}).get("currency", body.currency),
        )

    except HTTPException:
        raise
    except SquareError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception:
        logger.exception("Payment processing error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing payment",
        )
