import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    RECEIVED = "received"


class WhatsAppAccountConfig(Base):
    __tablename__ = "whatsapp_configs"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, unique=True, index=True)

    phone_number_id = Column(String, nullable=True)
    waba_id = Column(String, nullable=True)
    access_token = Column(String, nullable=True)
    verify_token = Column(String, nullable=True)

    auto_reply_enabled = Column(Boolean, default=False, nullable=False)
    ai_instructions = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WhatsAppConversation(Base):
    __tablename__ = "whatsapp_conversations"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)

    customer_phone = Column(String, nullable=False, index=True)
    customer_name = Column(String, nullable=True)
    unread_count = Column(Integer, default=0, nullable=False)
    last_message_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_message_preview = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer")
    messages = relationship("WhatsAppMessage", back_populates="conversation", cascade="all, delete-orphan")


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey("whatsapp_conversations.id"), nullable=False, index=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)

    direction = Column(Enum(MessageDirection), default=MessageDirection.OUTBOUND, nullable=False)
    status = Column(Enum(MessageStatus), default=MessageStatus.SENT, nullable=False)
    message_type = Column(String, default="text", nullable=False)  # text, document, template, image

    body = Column(Text, nullable=True)
    media_url = Column(String, nullable=True)
    wa_message_id = Column(String, nullable=True, index=True)
    ai_generated = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    conversation = relationship("WhatsAppConversation", back_populates="messages")
    customer = relationship("Customer")
