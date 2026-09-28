import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Customer, Invoice, Quotation
from app.pdf_generator import generate_invoice_pdf, generate_quotation_pdf
from app.whatsapp_models import (
    WhatsAppAccountConfig,
    WhatsAppConversation,
    WhatsAppMessage,
    MessageDirection,
    MessageStatus,
)
from app.whatsapp_assistant import (
    send_meta_whatsapp_message,
    process_incoming_whatsapp_message,
    generate_whatsapp_ai_reply,
)

logger = logging.getLogger("routers.whatsapp")

router = APIRouter(
    prefix="/api/whatsapp",
    tags=["whatsapp"],
)


# ==========================================================================
# Helpers
# ==========================================================================

def normalize_phone(phone: Optional[str]) -> str:
    """
    Normalize WhatsApp phone numbers for comparison.

    Examples:
        +923215772078 -> 923215772078
        923215772078  -> 923215772078
        +92 321 5772078 -> 923215772078
    """

    if not phone:
        return ""

    phone = str(phone).strip()

    # Keep digits only.
    digits = "".join(ch for ch in phone if ch.isdigit())

    return digits


def phone_variants(phone: Optional[str]) -> List[str]:
    """
    Return common variants of a phone number.

    Example:
        923215772078
        +923215772078
    """

    normalized = normalize_phone(phone)

    if not normalized:
        return []

    return [
        normalized,
        f"+{normalized}",
    ]


def find_conversation(
    db: Session,
    company_id: str,
    phone: str,
):
    """
    Find a WhatsApp conversation using normalized phone matching.

    First tries exact database lookup for:
        923...
        +923...

    Then falls back to Python normalization so values such as:
        +92 321 5772078
        +92-321-5772078
        923215772078

    can still match.
    """

    variants = phone_variants(phone)

    if not variants:
        return None

    # --------------------------------------------------------------
    # First: exact database lookup
    # --------------------------------------------------------------

    conv = (
        db.query(WhatsAppConversation)
        .filter(
            WhatsAppConversation.company_id == company_id,
            WhatsAppConversation.customer_phone.in_(variants),
        )
        .first()
    )

    if conv:
        return conv

    # --------------------------------------------------------------
    # Fallback: normalize all company conversations
    # --------------------------------------------------------------

    conversations = (
        db.query(WhatsAppConversation)
        .filter(
            WhatsAppConversation.company_id == company_id
        )
        .all()
    )

    normalized_target = normalize_phone(phone)

    for conversation in conversations:

        if normalize_phone(
            conversation.customer_phone
        ) == normalized_target:

            return conversation

    return None


# ==========================================================================
# Schemas
# ==========================================================================

class WhatsAppConfigSchema(BaseModel):
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    access_token: Optional[str] = None
    verify_token: Optional[str] = None
    auto_reply_enabled: bool = True
    ai_instructions: Optional[str] = None



class SendMessageSchema(BaseModel):
    recipient_phone: str
    message_text: str
    customer_id: Optional[str] = None


class SendDocumentSchema(BaseModel):
    recipient_phone: str
    doc_type: str  # "invoice" or "quotation"
    doc_id: str
    caption: Optional[str] = None


class AIReplySchema(BaseModel):
    recipient_phone: str
    incoming_text: str


# ==========================================================================
# WhatsApp Webhook
# ==========================================================================

@router.get("/webhook")
def verify_webhook(
    db: Session = Depends(get_db),
    hub_mode: Optional[str] = Query(
        None,
        alias="hub.mode",
    ),
    hub_verify_token: Optional[str] = Query(
        None,
        alias="hub.verify_token",
    ),
    hub_challenge: Optional[str] = Query(
        None,
        alias="hub.challenge",
    ),
):
    """
    Meta WhatsApp Cloud API webhook verification.

    Meta sends:

        hub.mode
        hub.verify_token
        hub.challenge

    We must return hub.challenge as plain text.
    """

    logger.info(
        "🔥 WhatsApp webhook verification request received"
    )

    logger.info(
        "Webhook verification mode=%r token_present=%s challenge_present=%s",
        hub_mode,
        bool(hub_verify_token),
        bool(hub_challenge),
    )

    if (
        hub_mode == "subscribe"
        and hub_verify_token
    ):

        config = (
            db.query(WhatsAppAccountConfig)
            .filter(
                WhatsAppAccountConfig.verify_token
                == hub_verify_token
            )
            .first()
        )

        # Existing configured token.
        if config:

            logger.info(
                "✅ WhatsApp webhook verified using database verify token"
            )

            return Response(
                content=hub_challenge or "OK",
                media_type="text/plain",
            )

        # Development fallback.
        #
        # You can remove this once Meta is fully configured
        # with the database verify token.
        if hub_verify_token == "ai_employee_os_token":

            logger.info(
                "✅ WhatsApp webhook verified using default development token"
            )

            return Response(
                content=hub_challenge or "OK",
                media_type="text/plain",
            )

    logger.warning(
        "❌ WhatsApp webhook verification failed"
    )

    raise HTTPException(
        status_code=403,
        detail="Verification token mismatch",
    )


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receives incoming WhatsApp messages and status events
    from Meta WhatsApp Cloud API.

    IMPORTANT:

    This endpoint must be publicly accessible because Meta
    sends POST requests directly to it.

    Public URL:

        https://YOUR-NGROK-DOMAIN/api/whatsapp/webhook
    """

    logger.info(
        "🔥🔥🔥 POST /api/whatsapp/webhook RECEIVED 🔥🔥🔥"
    )

    try:

        # --------------------------------------------------------------
        # Read JSON payload
        # --------------------------------------------------------------

        body = await request.json()

        logger.info(
            "WhatsApp webhook JSON parsed successfully"
        )

        # --------------------------------------------------------------
        # Basic payload information
        # --------------------------------------------------------------

        webhook_object = body.get("object")

        entries = body.get("entry", [])

        logger.info(
            "Webhook object=%r entries=%s",
            webhook_object,
            len(entries),
        )

        # --------------------------------------------------------------
        # Inspect Meta payload
        #
        # This is extremely useful while debugging because it tells
        # us exactly what Meta sent.
        # --------------------------------------------------------------

        for entry_index, entry in enumerate(entries):

            changes = entry.get("changes", [])

            logger.info(
                "Webhook entry[%s] changes=%s",
                entry_index,
                len(changes),
            )

            for change_index, change in enumerate(changes):

                field = change.get("field")

                value = change.get("value") or {}

                metadata = value.get("metadata") or {}

                phone_number_id = metadata.get(
                    "phone_number_id"
                )

                display_phone_number = metadata.get(
                    "display_phone_number"
                )

                messages = value.get(
                    "messages"
                ) or []

                statuses = value.get(
                    "statuses"
                ) or []

                logger.info(
                    "Webhook change[%s] field=%r "
                    "phone_number_id=%r "
                    "display_phone_number=%r "
                    "messages=%s "
                    "statuses=%s",
                    change_index,
                    field,
                    phone_number_id,
                    display_phone_number,
                    len(messages),
                    len(statuses),
                )

                # ------------------------------------------------------
                # Incoming messages
                # ------------------------------------------------------

                for message in messages:

                    wa_message_id = message.get(
                        "id"
                    )

                    sender = message.get(
                        "from"
                    )

                    message_type = message.get(
                        "type"
                    )

                    text_body = ""

                    if message_type == "text":

                        text_data = (
                            message.get("text")
                            or {}
                        )

                        text_body = (
                            text_data.get("body")
                            or ""
                        )

                    logger.info(
                        "📩 INCOMING WHATSAPP MESSAGE "
                        "from=%r "
                        "type=%r "
                        "wa_message_id=%r "
                        "text=%r",
                        sender,
                        message_type,
                        wa_message_id,
                        text_body,
                    )

                # ------------------------------------------------------
                # Message status updates
                # ------------------------------------------------------

                for status in statuses:

                    logger.info(
                        "📊 WHATSAPP STATUS "
                        "id=%r "
                        "status=%r "
                        "recipient=%r",
                        status.get("id"),
                        status.get("status"),
                        status.get("recipient_id"),
                    )

        # --------------------------------------------------------------
        # Process the actual webhook
        # --------------------------------------------------------------

        result = process_incoming_whatsapp_message(
            db,
            body,
        )

        logger.info(
            "✅ WhatsApp webhook processed successfully: %s",
            result,
        )

        return {
            "status": "ok",
            "result": result,
        }

    except Exception as e:

        logger.exception(
            "❌ ERROR handling WhatsApp webhook payload"
        )

        # During debugging, return HTTP 200 so Meta does not
        # repeatedly retry the same event while we inspect logs.
        #
        # After the integration is stable, you may change this
        # to HTTP 500 so Meta can retry failed events.
        return {
            "status": "ok",
            "note": f"Handled with notice: {str(e)}",
        }


# ==========================================================================
# WhatsApp Configuration
# ==========================================================================

@router.get("/config")
def get_whatsapp_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return WhatsApp configuration.

    IMPORTANT:
    Never return the WhatsApp access token or verify token
    to the frontend.
    """

    config = (
        db.query(WhatsAppAccountConfig)
        .filter(
            WhatsAppAccountConfig.company_id == current_user.company_id
        )
        .first()
    )

    if not config:
        config = WhatsAppAccountConfig(
            company_id=current_user.company_id,
            verify_token="ai_employee_os_token",
            auto_reply_enabled=True,
        )

        db.add(config)
        db.commit()
        db.refresh(config)

    return {
        "phone_number_id": config.phone_number_id,
        "waba_id": config.waba_id,
        "auto_reply_enabled": config.auto_reply_enabled,
        "ai_instructions": config.ai_instructions,
        "webhook_url": "/api/whatsapp/webhook",
    }


@router.post("/config")
def update_whatsapp_config(
    payload: WhatsAppConfigSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Save/update WhatsApp Cloud API configuration.

    Optional credentials are only changed when supplied, so updating
    auto_reply_enabled does not erase an existing access token.
    """

    config = (
        db.query(WhatsAppAccountConfig)
        .filter(
            WhatsAppAccountConfig.company_id == current_user.company_id
        )
        .first()
    )

    if not config:
        config = WhatsAppAccountConfig(
            company_id=current_user.company_id,
            verify_token="ai_employee_os_token",
            auto_reply_enabled=False,
        )
        db.add(config)
        db.flush()

    if payload.phone_number_id is not None:
        config.phone_number_id = payload.phone_number_id

    if payload.waba_id is not None:
        config.waba_id = payload.waba_id

    if payload.access_token is not None:
        config.access_token = payload.access_token

    if payload.verify_token is not None:
        config.verify_token = payload.verify_token

    config.auto_reply_enabled = payload.auto_reply_enabled

    if payload.ai_instructions is not None:
        config.ai_instructions = payload.ai_instructions

    db.commit()
    db.refresh(config)

    logger.info(
        "WhatsApp configuration updated for company_id=%s "
        "phone_number_id=%r waba_id=%r auto_reply=%s",
        current_user.company_id,
        config.phone_number_id,
        config.waba_id,
        config.auto_reply_enabled,
    )

    return {
        "status": "updated",
        "auto_reply_enabled": config.auto_reply_enabled,
    }



# ==========================================================================
# Conversations
# ==========================================================================

@router.get("/conversations")
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return all WhatsApp conversations for the current company.
    """

    conversations = (
        db.query(WhatsAppConversation)
        .filter(
            WhatsAppConversation.company_id
            == current_user.company_id
        )
        .order_by(
            WhatsAppConversation.last_message_at.desc()
        )
        .all()
    )

    return [
        {
            "id": c.id,

            "customer_id": c.customer_id,

            "customer_phone": c.customer_phone,

            "customer_name": (
                c.customer_name
                or c.customer_phone
            ),

            "unread_count": c.unread_count,

            "last_message_at": (
                c.last_message_at.isoformat()
                if c.last_message_at
                else None
            ),

            "last_message_preview": (
                c.last_message_preview
            ),
        }
        for c in conversations
    ]


# ==========================================================================
# Conversation Messages
# ==========================================================================

@router.get(
    "/conversations/{phone}/messages"
)
def get_conversation_messages(
    phone: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return all messages for a WhatsApp conversation.
    """

    logger.info(
        "Getting WhatsApp messages "
        "for phone=%r normalized=%r",
        phone,
        normalize_phone(phone),
    )

    # --------------------------------------------------------------
    # Find conversation using normalized phone number.
    # --------------------------------------------------------------

    conv = find_conversation(
        db=db,
        company_id=current_user.company_id,
        phone=phone,
    )

    if not conv:

        logger.warning(
            "WhatsApp conversation NOT FOUND "
            "phone=%r normalized=%r company_id=%s",
            phone,
            normalize_phone(phone),
            current_user.company_id,
        )

        return []

    logger.info(
        "WhatsApp conversation FOUND "
        "id=%s phone=%r",
        conv.id,
        conv.customer_phone,
    )

    # --------------------------------------------------------------
    # Clear unread count when conversation is opened.
    # --------------------------------------------------------------

    conv.unread_count = 0

    db.commit()

    # --------------------------------------------------------------
    # Get messages
    # --------------------------------------------------------------

    messages = (
        db.query(WhatsAppMessage)
        .filter(
            WhatsAppMessage.conversation_id
            == conv.id
        )
        .order_by(
            WhatsAppMessage.created_at.asc()
        )
        .all()
    )

    logger.info(
        "WhatsApp message count "
        "for conversation %s: %s",
        conv.id,
        len(messages),
    )

    return [
        {
            "id": m.id,

            "direction": m.direction.value,

            "status": m.status.value,

            "message_type": m.message_type,

            "body": m.body,

            "media_url": m.media_url,

            "ai_generated": m.ai_generated,

            "created_at": (
                m.created_at.isoformat()
                if m.created_at
                else None
            ),
        }
        for m in messages
    ]


# ==========================================================================
# Send WhatsApp Message
# ==========================================================================

@router.post("/send")
def send_whatsapp_message_route(
    payload: SendMessageSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Send an outbound WhatsApp message through Meta Cloud API.
    """

    config = (
        db.query(WhatsAppAccountConfig)
        .filter(
            WhatsAppAccountConfig.company_id
            == current_user.company_id
        )
        .first()
    )

    if not config:

        raise HTTPException(
            status_code=400,
            detail="WhatsApp configuration not found.",
        )

    phone_id = (
        config.phone_number_id
        or ""
    )

    token = (
        config.access_token
        or ""
    )

    if not phone_id:

        raise HTTPException(
            status_code=400,
            detail="WhatsApp Phone Number ID is not configured.",
        )

    if not token:

        raise HTTPException(
            status_code=400,
            detail="WhatsApp access token is not configured.",
        )

    recipient_phone = (
        payload.recipient_phone.strip()
    )

    normalized_phone = normalize_phone(
        recipient_phone
    )

    if not normalized_phone:

        raise HTTPException(
            status_code=400,
            detail="Invalid recipient phone number.",
        )

    # --------------------------------------------------------------
    # Find customer
    # --------------------------------------------------------------

    customer = None

    phone_digits = normalized_phone

    customers = (
        db.query(Customer)
        .filter(
            Customer.company_id
            == current_user.company_id
        )
        .all()
    )

    for candidate in customers:

        if normalize_phone(
            candidate.phone
        ) == phone_digits:

            customer = candidate
            break

    # --------------------------------------------------------------
    # Find or create conversation
    # --------------------------------------------------------------

    conv = find_conversation(
        db=db,
        company_id=current_user.company_id,
        phone=recipient_phone,
    )

    if not conv:

        conv = WhatsAppConversation(
            company_id=current_user.company_id,

            customer_id=(
                customer.id
                if customer
                else None
            ),

            customer_phone=normalized_phone,

            customer_name=(
                customer.name
                if customer
                else recipient_phone
            ),

            unread_count=0,
        )

        db.add(conv)

        db.flush()

    # --------------------------------------------------------------
    # Send through Meta
    # --------------------------------------------------------------

    res = send_meta_whatsapp_message(
        phone_number_id=phone_id,
        access_token=token,
        recipient_phone=recipient_phone,
        message_text=payload.message_text,
    )

    logger.info(
        "WhatsApp outbound result: %s",
        res,
    )

    # --------------------------------------------------------------
    # Store outbound message
    # --------------------------------------------------------------

    message_status = (
        MessageStatus.SENT
        if res.get("status")
        in ["sent", "simulated"]
        else MessageStatus.FAILED
    )

    msg = WhatsAppMessage(
        company_id=current_user.company_id,

        conversation_id=conv.id,

        customer_id=(
            customer.id
            if customer
            else None
        ),

        direction=MessageDirection.OUTBOUND,

        status=message_status,

        message_type="text",

        body=payload.message_text,

        wa_message_id=res.get(
            "wa_message_id"
        ),

        ai_generated=False,
    )

    db.add(msg)

    # --------------------------------------------------------------
    # Update conversation
    # --------------------------------------------------------------

    conv.last_message_at = datetime.utcnow()

    conv.last_message_preview = (
        payload.message_text
    )

    db.commit()

    db.refresh(msg)

    return {
        "status": "success",

        "message_id": msg.id,

        "wa_result": res,
    }


# ==========================================================================
# AI Suggested Reply
# ==========================================================================

@router.post("/ai-suggest")
def suggest_ai_reply(
    payload: AIReplySchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate an AI suggested WhatsApp reply.
    """

    config = (
        db.query(WhatsAppAccountConfig)
        .filter(
            WhatsAppAccountConfig.company_id
            == current_user.company_id
        )
        .first()
    )

    # --------------------------------------------------------------
    # Find conversation
    # --------------------------------------------------------------

    conv = find_conversation(
        db=db,
        company_id=current_user.company_id,
        phone=payload.recipient_phone,
    )

    formatted_history = []

    if conv:

        msgs = (
            db.query(WhatsAppMessage)
            .filter(
                WhatsAppMessage.conversation_id
                == conv.id
            )
            .order_by(
                WhatsAppMessage.created_at.desc()
            )
            .limit(5)
            .all()
        )

        formatted_history = [
            {
                "role": (
                    "user"
                    if m.direction
                    == MessageDirection.INBOUND
                    else "assistant"
                ),

                "text": m.body or "",
            }
            for m in reversed(msgs)
        ]

    # --------------------------------------------------------------
    # Generate AI reply
    # --------------------------------------------------------------

    suggested_text = generate_whatsapp_ai_reply(
        db=db,

        company_id=current_user.company_id,

        customer_phone=payload.recipient_phone,

        incoming_text=payload.incoming_text,

        conversation_history=formatted_history,

        custom_instructions=(
            config.ai_instructions
            if config
            else None
        ),
    )

    return {
        "suggested_reply": suggested_text
    }