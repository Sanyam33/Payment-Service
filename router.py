from fastapi import APIRouter, Request
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import stripe, httpx 
import os

from models import Transaction
from schemas import (
    TransactionCreateRequest,
    TransactionCreateResponse,
    TrxStatus,
    TrxPaymentMethod,
)
from db import get_db

load_dotenv()
payment_router = APIRouter(prefix="/api/v1/transactions", tags=["Transaction"])
async_client = httpx.AsyncClient()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
SUCCESS_URL = os.getenv("NODE_WEBHOOK_URL")
CANCEL_URL = "http://localhost:8000/payment-cancel"
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
NODE_SECRET = os.getenv("NODE_SECRET")
NODE_WEBHOOK_URL = os.getenv("NODE_WEBHOOK_URL")


@payment_router.post("/create", response_model=TransactionCreateResponse)
async def create_transaction(
    payload: TransactionCreateRequest,
    db: Session = Depends(get_db),
):
    # 1. Validation Logic
    if payload.payment_method != TrxPaymentMethod.stripe:
        raise HTTPException(status_code=400, detail="Only Stripe is supported")

    # Prevent duplicate order processing in our DB
    existing = db.query(Transaction).filter(Transaction.order_id == payload.order_id).first()
    if existing:
        return TransactionCreateResponse(
            transaction_id=existing.id,
            status=existing.status,
            payment_id=existing.payment_id,
            payment_url=None, # Or retrieve existing session URL if needed
        )

    try:
        # 2. Stripe Session Creation with Idempotency
        # We use the order_id as the idempotency key to prevent double charges
        session = stripe.checkout.Session.create(
            payment_method_types=["upi"],
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "inr",
                        "product_data": {"name": "Wallet Topup"},
                        # Safety: round to nearest integer to avoid float precision issues
                        "unit_amount": int(round(payload.amount * 100)),
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "order_id": str(payload.order_id),
                "user_id": str(payload.user_id),
            },
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            idempotency_key=f"checkout_{payload.order_id}"
        )
    except stripe.error.StripeError as e:
        # Catch specific Stripe errors (Card declined, invalid params, etc.)
        raise HTTPException(status_code=400, detail=f"Stripe Error: {e.user_message or str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error during payment creation")

    # 3. Save Pending Transaction to DB
    try:
        new_trx = Transaction(
            user_id=payload.user_id,
            order_id=payload.order_id,
            type=payload.type,
            amount=payload.amount,
            payment_method=payload.payment_method,
            payment_id=session.id,
            status=TrxStatus.pending,
        )
        db.add(new_trx)
        db.commit()
        db.refresh(new_trx)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while saving transaction")

    return TransactionCreateResponse(
        transaction_id=new_trx.id,
        status=new_trx.status,
        payment_id=new_trx.payment_id,
        payment_url=session.url,
    )



# @payment_router.post("/stripe-webhook")
# async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
#     payload = await request.body()
#     sig_header = request.headers.get("stripe-signature")

#     try:
#         event = stripe.Webhook.construct_event(
#             payload=payload,
#             sig_header=sig_header,
#             secret=STRIPE_WEBHOOK_SECRET,
#         )
#     except Exception as e:
#         print("Webhook error:", e)
#         raise HTTPException(status_code=400, detail="Invalid webhook signature")

#     if event["type"] == "checkout.session.completed":
#         session = event["data"]["object"]
#         payment_id = session["id"]

#         trx = db.query(Transaction).filter(
#             Transaction.payment_id == payment_id
#         ).first()

#         if trx:
#             trx.status = TrxStatus.completed
#             db.commit()
#             print("Transaction marked completed:", trx.id)

#     return {"status": "ok"}





# @payment_router.post("/stripe-webhook")
# async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
#     payload = await request.body()
#     sig_header = request.headers.get("stripe-signature")

#     try:
#         event = stripe.Webhook.construct_event(
#             payload=payload,
#             sig_header=sig_header,
#             secret=STRIPE_WEBHOOK_SECRET,
#         )
#     except Exception as e:
#         print("Webhook error:", e)
#         raise HTTPException(status_code=400, detail="Invalid webhook signature")

#     if event["type"] == "checkout.session.completed":
#         session = event["data"]["object"]
#         payment_id = session["id"]

#         trx = db.query(Transaction).filter(
#             Transaction.payment_id == payment_id
#         ).first()

#         if not trx:
#             return {"status": "transaction not found"}

#         # Update DB
#         trx.status = TrxStatus.completed
#         db.commit()

#         # -----------------------------
#         # REAL WAY: Notify Node backend
#         # -----------------------------
#         try:
#             response = requests.post(
#                 NODE_WEBHOOK_URL,
#                 json={
#                     "transaction_id": str(trx.id),
#                     "user_id": str(trx.user_id),
#                     "amount": trx.amount,
#                     "status": "completed",
#                 },
#                 headers={
#                     "x-internal-secret": NODE_SECRET
#                 },
#                 timeout=5,
#             )
#             print("Node notified:", response.status_code)
#         except Exception as e:
#             print("Failed to notify Node:", e)

#     return {"status": "ok"}




@payment_router.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Signature verification failed")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        payment_id = session["id"]

        try:
            # 1. Lock the row for update to handle concurrent webhooks
            trx = db.query(Transaction).filter(
                Transaction.payment_id == payment_id
            ).with_for_update().first()

            if not trx:
                return {"status": "transaction_not_found"}

            # 2. Idempotency Check: If already completed, stop here.
            if trx.status == TrxStatus.completed:
                return {"status": "already_processed"}

            # 3. Update local status
            trx.status = TrxStatus.completed
            db.commit()

            # 4. Notify your Wallet System (Hono/TSX) using httpx
            # We do this AFTER the DB commit to ensure our record is safe
            internal_payload = {
                "order_id": str(trx.order_id),
                "transaction_id": str(trx.id),
                "user_id": str(trx.user_id),
                "amount": float(trx.amount),
                "status": "success"
            }
            
            # Using httpx to call your other system asynchronously
            # We don't 'await' this if we want to return 200 to Stripe immediately, 
            # but usually, it's safer to await or use BackgroundTasks.
            response = await async_client.post(
                # f"{WALLET_SYSTEM_URL}/credit-wallet", 
                NODE_WEBHOOK_URL,
                json=internal_payload,
                headers={"X-Internal-Secret": NODE_SECRET},
                timeout=5,
            )
            
            if response.status_code != 200:
                print(f"Alert: Wallet system failed to credit user {trx.user_id}")
                # Optional: You could raise an error here so Stripe retries

        except Exception as e:
            db.rollback()
            print(f"Database error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    return {"status": "ok"}



# API_TOKEN = os.getenv("WISE_API_KEY")
# BASE_URL = "https://api.sandbox.transferwise.tech"

# @payment_router.post("/wise")
# async def get_profile_id():
#     print(API_TOKEN)
#     headers = {"Authorization": f"Bearer {API_TOKEN}"}
#     async with httpx.AsyncClient() as client:
#         response = await client.get(f"{BASE_URL}/v1/profiles", headers=headers)
#         profiles = response.json()
#         # return profiles
#         for profile in profiles:
#             print(f"Type: {profile['type']}, ID: {profile['id']}")
#             Type: personal, ID: 29809792
#             Type: business, ID: 29809793

# WISE_API_TOKEN = os.getenv("WISE_API_KEY")
# WISE_BASE_URL = "https://api.sandbox.transferwise.tech"
# PROFILE_ID = 29809793 # Obtained from Step 1

# headers = {
#     "Authorization": f"Bearer {WISE_API_TOKEN}",
#     "Content-Type": "application/json"
# }

@payment_router.get("/wallet/balances")
async def get_wise_balances():
    """
    Fetches all active balances for the business profile.
    """
    url = f"{WISE_BASE_URL}/v4/profiles/{PROFILE_ID}/balances?types=STANDARD"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)
            
        return response.json()


@payment_router.post("/wallet/test-topup")
async def simulate_topup(amount: float, currency: str = "GBP"):
    """
    Adds fake money to your sandbox balance for testing.
    """
    # First, you need the balanceId for that specific currency
    # (Usually found by calling the balances endpoint above)
    balance_id = 355956

    url = f"{WISE_BASE_URL}/v1/simulation/balance/topup"
    payload = {
        "profileId": int(PROFILE_ID),
        "balanceId": int(balance_id),
        "currency": currency,
        "amount": amount,
        "channel": "CARD"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        return response.json()