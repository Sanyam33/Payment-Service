from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional


from enum import Enum

class TrxType(str, Enum):
    credit = "credit"
    debit = "debit"
    withdrawal = "withdrawal"
    refund = "refund"
    earnings = "earnings"
    platform_fee = "platform_fee"


class TrxStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class TrxPaymentMethod(str, Enum):
    stripe = "stripe"
    paypal = "paypal"
    wallet = "wallet"



class TransactionCreateRequest(BaseModel):
    user_id: UUID
    order_id: int = Field(..., description="Internal order or topup id from Node")
    amount: float = Field(..., gt=0)
    type: TrxType = TrxType.credit
    payment_method: TrxPaymentMethod = TrxPaymentMethod.stripe

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "9f4c9f25-9d5c-4fa1-9a7d-123456789abc",
                "order_id": 101,
                "amount": 50.0,
                "type": "credit",
                "payment_method": "stripe"
            }
        }


class TransactionCreateResponse(BaseModel):
    transaction_id: UUID
    status: TrxStatus
    payment_id: str
    payment_url: Optional[str] = None
    

class StripePaymentData(BaseModel):
    id: str
    status: str


class StripeWebhookData(BaseModel):
    object: str
    id: str
    data: dict
    type: str


class TransactionStatusUpdate(BaseModel):
    transaction_id: UUID
    payment_id: str
    status: TrxStatus
