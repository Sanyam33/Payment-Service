from sqlalchemy import (
    Column,
    String,
    Float,
    BigInteger,
    DateTime,
    Enum as SqlEnum,
    func,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
import uuid
from db import Base
from datetime import datetime
from schemas import TrxType, TrxStatus, TrxPaymentMethod


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    order_id = Column(BigInteger, nullable=False, index=True)

    type = Column(SqlEnum(TrxType, name="trx_type"), nullable=False)

    amount = Column(Float, nullable=False)

    balance_after = Column(Float, nullable=True)

    payment_method = Column(
        SqlEnum(TrxPaymentMethod, name="trx_payment_method"),
        nullable=False
    )

    payment_id = Column(String, nullable=True, index=True)

    status = Column(SqlEnum(TrxStatus, name="trx_status"), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.timezone('UTC', func.now()),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.timezone('UTC', func.now()),
        onupdate=func.timezone('UTC', func.now()),
        nullable=False
    )


# Useful composite indexes (optional but recommended)
Index("idx_transactions_user_status", Transaction.user_id, Transaction.status)
Index("idx_transactions_payment_id", Transaction.payment_id)
Index("idx_transactions_order_id", Transaction.order_id)
