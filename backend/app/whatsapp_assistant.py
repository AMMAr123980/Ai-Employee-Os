import logging
import json
import urllib.request
import urllib.error

from datetime import datetime
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session
import openai

from app.config import settings
from app.models import Customer, Invoice, Quotation
from app.whatsapp_models import (
    WhatsAppAccountConfig,
    WhatsAppConversation,
    WhatsAppMessage,
    MessageDirection,
    MessageStatus,
)


logger = logging.getLogger("whatsapp_assistant")


# ============================================================
# PHONE NUMBER NORMALIZATION
# ============================================================

def normalize_phone(phone: Optional[str]) -> str:
    """
    Convert WhatsApp phone numbers to digits only.

    Examples:

        +923215772078
        923215772078
        +92 321 5772078
        +92-321-5772078

    All become:

        923215772078
    """

    if not phone:
        return ""

    return "".join(
        ch for ch in str(phone)
        if ch.isdigit()
    )


# ============================================================
# FIND CUSTOMER BY NORMALIZED PHONE
# ============================================================

def find_customer_by_phone(
    db: Session,
    company_id: str,
    phone: str,
) -> Optional[Customer]:
    """
    Find customer even when database and Meta use different
    phone formatting.
    """

    normalized_phone = normalize_phone(phone)

    if not normalized_phone:
        return None

    customers = (
        db.query(Customer)
        .filter(
            Customer.company_id == company_id
        )
        .all()
    )

    for customer in customers:

        stored_phone = normalize_phone(
            customer.phone
        )

        if stored_phone == normalized_phone:
            return customer

    return None


# ============================================================
# FIND WHATSAPP CONVERSATION BY NORMALIZED PHONE
# ============================================================

def find_whatsapp_conversation_by_phone(
    db: Session,
    company_id: str,
    phone: str,
) -> Optional[WhatsAppConversation]:
    """
    Find conversation regardless of whether phone is stored as:

        +923215772078

    or:

        923215772078
    """

    normalized_phone = normalize_phone(phone)

    if not normalized_phone:
        return None

    conversations = (
        db.query(WhatsAppConversation)
        .filter(
            WhatsAppConversation.company_id == company_id
        )
        .all()
    )

    for conversation in conversations:

        stored_phone = normalize_phone(
            conversation.customer_phone
        )

        if stored_phone == normalized_phone:
            return conversation

    return None


# ============================================================
# SEND WHATSAPP MESSAGE
# ============================================================

def send_meta_whatsapp_message(
    phone_number_id: str,
    access_token: str,
    recipient_phone: str,
    message_text: str,
    media_url: Optional[str] = None,
    filename: Optional[str] = "document.pdf",
) -> Dict[str, Any]:
    """
    Send WhatsApp message through Meta Cloud API.

    If credentials are missing, use simulated mode.
    """

    clean_phone = normalize_phone(
        recipient_phone
    )

    if not clean_phone:
        return {
            "status": "failed",
            "error": "Invalid recipient phone number",
        }

    # ========================================================
    # SIMULATED MODE
    # ========================================================

    if not phone_number_id or not access_token:

        logger.info(
            "[SIMULATED WHATSAPP] "
            "To: %s, Text: %s, Media: %s",
            clean_phone,
            message_text,
            media_url,
        )

        return {
            "status": "simulated",
            "wa_message_id": (
                f"sim_wa_{datetime.utcnow().timestamp()}"
            ),
            "recipient": clean_phone,
            "body": message_text,
        }

    # ========================================================
    # META API URL
    # ========================================================

    url = (
        f"https://graph.facebook.com/v19.0/"
        f"{phone_number_id}/messages"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # ========================================================
    # DOCUMENT MESSAGE
    # ========================================================

    if media_url:

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "document",
            "document": {
                "link": media_url,
                "filename": filename or "document.pdf",
                "caption": message_text or "",
            },
        }

    # ========================================================
    # TEXT MESSAGE
    # ========================================================

    else:

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "text",
            "text": {
                "body": message_text,
            },
        }

    logger.info(
        "📤 Sending WhatsApp message to=%s",
        clean_phone,
    )

    # ========================================================
    # SEND REQUEST
    # ========================================================

    try:

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:

            response_body = (
                response.read()
                .decode("utf-8")
            )

            data = json.loads(
                response_body
            )

            wa_id = (
                data.get(
                    "messages",
                    [{}],
                )[0].get(
                    "id",
                    "wa_id_unknown",
                )
            )

            logger.info(
                "✅ Meta WhatsApp message sent "
                "wa_message_id=%s",
                wa_id,
            )

            return {
                "status": "sent",
                "wa_message_id": wa_id,
                "response": data,
            }

    except urllib.error.HTTPError as e:

        error_body = e.read().decode(
            "utf-8"
        )

        logger.error(
            "❌ Meta WhatsApp API HTTPError "
            "code=%s body=%s",
            e.code,
            error_body,
        )

        return {
            "status": "failed",
            "error": error_body,
            "wa_message_id": (
                f"err_wa_{datetime.utcnow().timestamp()}"
            ),
        }

    except Exception as exc:

        logger.exception(
            "❌ Meta WhatsApp API error"
        )

        return {
            "status": "failed",
            "error": str(exc),
            "wa_message_id": (
                f"err_wa_{datetime.utcnow().timestamp()}"
            ),
        }


# ============================================================
# GENERATE AI WHATSAPP REPLY
# ============================================================

def generate_whatsapp_ai_reply(
    db: Session,
    company_id: str,
    customer_phone: str,
    incoming_text: str,
    conversation_history: List[Dict[str, str]],
    custom_instructions: Optional[str] = None,
) -> str:
    """
    Generate a context-aware AI response for an incoming
    WhatsApp message.

    Uses the unified LLM router (complete_text) which
    supports Gemini, OpenAI, and Anthropic based on the
    AI_PROVIDER setting.
    """

    from app.llm_provider import complete_text

    # ========================================================
    # FIND CUSTOMER
    # ========================================================

    customer = find_customer_by_phone(
        db=db,
        company_id=company_id,
        phone=customer_phone,
    )

    # ========================================================
    # CUSTOMER CONTEXT
    # ========================================================

    customer_info = (
        f"Customer Name: "
        f"{customer.name if customer else 'Unknown'}\n"
    )

    if customer:

        customer_info += (
            f"Company: "
            f"{customer.company or 'N/A'}\n"
        )

        pipeline_stage = getattr(
            customer,
            "pipeline_stage",
            None,
        )

        if pipeline_stage:

            stage_value = getattr(
                pipeline_stage,
                "value",
                str(pipeline_stage),
            )

            customer_info += (
                f"Pipeline Stage: "
                f"{stage_value}\n"
            )

        # ====================================================
        # CUSTOMER INVOICES
        # ====================================================

        invoices = (
            db.query(Invoice)
            .filter(
                Invoice.company_id == company_id,
                Invoice.customer_id == customer.id,
            )
            .all()
        )

        if invoices:

            invoice_items = []

            for invoice in invoices[:3]:

                invoice_status = getattr(
                    invoice.status,
                    "value",
                    str(invoice.status),
                )

                invoice_items.append(
                    f"#{invoice.number} "
                    f"({invoice_status}, "
                    f"Total: {invoice.currency} "
                    f"{invoice.total})"
                )

            customer_info += (
                "Recent Invoices: "
                + ", ".join(invoice_items)
                + "\n"
            )

    # ========================================================
    # KNOWLEDGE BASE CONTEXT (if available)
    # ========================================================

    kb_context = ""

    try:
        from app.document_store import search as kb_search

        kb_results = kb_search(
            db=db,
            company_id=company_id,
            query=incoming_text,
            top_k=3,
        )

        if kb_results:
            kb_context = (
                "\n\nRELEVANT KNOWLEDGE BASE INFO:\n"
            )
            for chunk in kb_results:
                text = chunk.get(
                    "content",
                    chunk.get("text", ""),
                )
                if text:
                    kb_context += f"- {text[:300]}\n"

    except Exception as kb_err:
        logger.warning(
            "Knowledge base lookup skipped: %s",
            kb_err,
        )

    # ========================================================
    # CONVERSATION HISTORY
    # ========================================================

    history_str = ""

    for msg in conversation_history[-5:]:

        history_str += (
            f"{msg['role'].upper()}: "
            f"{msg['text']}\n"
        )

    # ========================================================
    # SYSTEM PROMPT
    # ========================================================

    system_prompt = (
        f"You are the AI WhatsApp Assistant for "
        f"{settings.company_name}.\n"
        f"Goal: Provide concise, professional, "
        f"friendly, and helpful WhatsApp support.\n"
        f"Rules:\n"
        f"- Answer based on the customer's ACTUAL "
        f"question or message.\n"
        f"- If they ask about meetings, help schedule "
        f"a meeting.\n"
        f"- If they ask about pricing, share pricing "
        f"info.\n"
        f"- If they ask about invoices, share invoice "
        f"details.\n"
        f"- Keep response under 350 characters.\n"
        f"- Do NOT output markdown titles or wall of "
        f"text.\n"
        f"- Do NOT give generic templated responses.\n"
        f"- Be conversational and human-like.\n"
        f"{custom_instructions or ''}\n\n"
        f"CUSTOMER CONTEXT:\n"
        f"{customer_info}"
        f"{kb_context}"
    )

    # ========================================================
    # USER PROMPT
    # ========================================================

    user_prompt = (
        f"Recent Conversation History:\n"
        f"{history_str}\n"
        f"New Customer Message: {incoming_text}\n\n"
        f"Reply to the customer's message directly "
        f"and helpfully. Do NOT send a generic "
        f"'thank you for reaching out' response. "
        f"Address what they actually said."
    )

    # ========================================================
    # CALL UNIFIED LLM ROUTER & SMART CONTEXTUAL AI
    # ========================================================

    try:
        reply = complete_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )

        logger.info(
            "AI WhatsApp reply generated via %s",
            settings.ai_provider,
        )

        return reply

    except Exception as e:
        logger.error(
            "LLM error in generate_whatsapp_ai_reply: %s",
            e,
        )
        from app.llm_provider import smart_contextual_fallback
        return smart_contextual_fallback(user_prompt, system_prompt)


# ============================================================
# PROCESS INCOMING WHATSAPP WEBHOOK
# ============================================================

def process_incoming_whatsapp_message(
    db: Session,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Process Meta WhatsApp webhook.

    Handles:

    1. Incoming customer messages
    2. Outbound message status updates
    3. Customer creation
    4. Conversation creation
    5. Inbound message storage
    6. AI auto replies
    """

    logger.info(
        "🚀 Processing incoming WhatsApp webhook"
    )

    results = []

    entries = payload.get(
        "entry",
        [],
    )

    # ========================================================
    # LOOP ENTRIES
    # ========================================================

    for entry in entries:

        changes = entry.get(
            "changes",
            [],
        )

        for change in changes:

            value = change.get(
                "value",
                {},
            ) or {}

            messages = value.get(
                "messages",
                [],
            ) or []

            statuses = value.get(
                "statuses",
                [],
            ) or []

            contacts = value.get(
                "contacts",
                [],
            ) or []

            metadata = value.get(
                "metadata",
                {},
            ) or {}

            phone_number_id = metadata.get(
                "phone_number_id"
            )

            logger.info(
                "📦 Webhook phone_number_id=%s "
                "messages=%s statuses=%s",
                phone_number_id,
                len(messages),
                len(statuses),
            )

            # =================================================
            # FIND WHATSAPP CONFIG
            # =================================================

            config = None

            if phone_number_id:

                config = (
                    db.query(
                        WhatsAppAccountConfig
                    )
                    .filter(
                        WhatsAppAccountConfig.phone_number_id
                        == phone_number_id
                    )
                    .first()
                )

            # Fallback for single-account setup

            if not config:

                config = (
                    db.query(
                        WhatsAppAccountConfig
                    )
                    .first()
                )

                if config:

                    logger.warning(
                        "⚠️ No exact WhatsApp config matched "
                        "phone_number_id=%s. "
                        "Using first configuration.",
                        phone_number_id,
                    )

            if not config:

                logger.error(
                    "❌ No WhatsApp configuration found"
                )

                continue

            logger.info(
                "✅ WhatsApp config found "
                "company_id=%s phone_number_id=%s",
                config.company_id,
                config.phone_number_id,
            )

            # =================================================
            # 1. MESSAGE STATUS UPDATES
            # =================================================

            for status_event in statuses:

                wa_message_id = status_event.get(
                    "id"
                )

                status_value = (
                    status_event.get(
                        "status"
                    )
                    or ""
                ).lower()

                if not wa_message_id:
                    continue

                status_map = {
                    "sent": MessageStatus.SENT,
                    "delivered": MessageStatus.DELIVERED,
                    "read": MessageStatus.READ,
                    "failed": MessageStatus.FAILED,
                }

                new_status = status_map.get(
                    status_value
                )

                if not new_status:

                    logger.warning(
                        "⚠️ Unknown WhatsApp status=%s "
                        "message_id=%s",
                        status_value,
                        wa_message_id,
                    )

                    continue

                existing_message = (
                    db.query(
                        WhatsAppMessage
                    )
                    .filter(
                        WhatsAppMessage.wa_message_id
                        == wa_message_id
                    )
                    .first()
                )

                if not existing_message:

                    logger.warning(
                        "⚠️ Status received for unknown "
                        "WhatsApp message=%s",
                        wa_message_id,
                    )

                    continue

                existing_message.status = (
                    new_status
                )

                db.commit()

                logger.info(
                    "📊 WhatsApp message status updated "
                    "id=%s status=%s",
                    wa_message_id,
                    status_value,
                )

                results.append(
                    {
                        "status": "updated",
                        "message_id": existing_message.id,
                        "wa_message_id": wa_message_id,
                        "new_status": status_value,
                    }
                )

            # =================================================
            # CONTACT MAP
            # =================================================

            contact_map = {
                contact.get("wa_id"):
                    contact.get(
                        "profile",
                        {}
                    ).get("name")
                for contact in contacts
                if contact.get("wa_id")
            }

            # =================================================
            # 2. INCOMING CUSTOMER MESSAGES
            # =================================================

            for msg in messages:

                from_phone = msg.get(
                    "from"
                )

                msg_id = msg.get(
                    "id"
                )

                msg_type = msg.get(
                    "type",
                    "text",
                )

                logger.info(
                    "📩 INCOMING WHATSAPP MESSAGE "
                    "from=%s type=%s id=%s",
                    from_phone,
                    msg_type,
                    msg_id,
                )

                # ------------------------------------------------
                # Validate
                # ------------------------------------------------

                if not from_phone or not msg_id:

                    logger.warning(
                        "⚠️ Ignoring malformed WhatsApp message: %s",
                        msg,
                    )

                    continue

                # =================================================
                # NORMALIZE PHONE
                # =================================================

                normalized_from_phone = (
                    normalize_phone(
                        from_phone
                    )
                )

                logger.info(
                    "📱 PHONE NORMALIZATION "
                    "original=%s normalized=%s",
                    from_phone,
                    normalized_from_phone,
                )

                # =================================================
                # DUPLICATE CHECK
                # =================================================

                existing_message = (
                    db.query(
                        WhatsAppMessage
                    )
                    .filter(
                        WhatsAppMessage.wa_message_id
                        == msg_id
                    )
                    .first()
                )

                if existing_message:

                    logger.info(
                        "⏭️ Duplicate WhatsApp message ignored "
                        "wa_message_id=%s",
                        msg_id,
                    )

                    continue

                # =================================================
                # EXTRACT MESSAGE BODY
                # =================================================

                body = ""

                if msg_type == "text":

                    body = (
                        msg.get(
                            "text",
                            {}
                        ).get(
                            "body",
                            ""
                        )
                    )

                elif msg_type == "document":

                    body = (
                        "[Document] "
                        + msg.get(
                            "document",
                            {}
                        ).get(
                            "filename",
                            "File",
                        )
                    )

                elif msg_type == "image":

                    body = "[Image message]"

                elif msg_type == "audio":

                    body = "[Audio message]"

                elif msg_type == "video":

                    body = "[Video message]"

                elif msg_type == "location":

                    body = "[Location message]"

                elif msg_type == "contacts":

                    body = "[Contact message]"

                else:

                    body = (
                        f"[{msg_type.capitalize()} message]"
                    )

                logger.info(
                    "📝 WhatsApp message body=%r",
                    body,
                )

                # =================================================
                # CUSTOMER NAME
                # =================================================

                sender_name = (
                    contact_map.get(
                        from_phone
                    )
                    or f"WhatsApp User "
                       f"({normalized_from_phone})"
                )

                # =================================================
                # FIND CUSTOMER
                # =================================================

                customer = find_customer_by_phone(
                    db=db,
                    company_id=config.company_id,
                    phone=normalized_from_phone,
                )

                if customer:

                    logger.info(
                        "👤 CUSTOMER FOUND "
                        "id=%s name=%s stored_phone=%s",
                        customer.id,
                        customer.name,
                        customer.phone,
                    )

                else:

                    logger.info(
                        "👤 CUSTOMER NOT FOUND. "
                        "Creating customer phone=%s",
                        normalized_from_phone,
                    )

                    customer = Customer(
                        company_id=config.company_id,
                        name=sender_name,
                        phone=normalized_from_phone,
                        notes=(
                            "Created via incoming "
                            "WhatsApp message"
                        ),
                    )

                    db.add(customer)

                    db.flush()

                    logger.info(
                        "👤 CUSTOMER CREATED "
                        "id=%s phone=%s",
                        customer.id,
                        customer.phone,
                    )

                # =================================================
                # FIND CONVERSATION
                # =================================================

                conversation = (
                    find_whatsapp_conversation_by_phone(
                        db=db,
                        company_id=config.company_id,
                        phone=normalized_from_phone,
                    )
                )

                if conversation:

                    logger.info(
                        "💬 EXISTING CONVERSATION FOUND "
                        "id=%s stored_phone=%s "
                        "incoming_phone=%s",
                        conversation.id,
                        conversation.customer_phone,
                        normalized_from_phone,
                    )

                else:

                    logger.info(
                        "💬 CONVERSATION NOT FOUND. "
                        "Creating conversation "
                        "phone=%s",
                        normalized_from_phone,
                    )

                    conversation = (
                        WhatsAppConversation(
                            company_id=config.company_id,
                            customer_id=customer.id,
                            customer_phone=(
                                normalized_from_phone
                            ),
                            customer_name=sender_name,
                            unread_count=0,
                        )
                    )

                    db.add(conversation)

                    db.flush()

                    logger.info(
                        "💬 CONVERSATION CREATED "
                        "id=%s phone=%s",
                        conversation.id,
                        conversation.customer_phone,
                    )

                # =================================================
                # CONNECT CUSTOMER
                # =================================================

                conversation.customer_id = (
                    customer.id
                )

                if sender_name:

                    conversation.customer_name = (
                        sender_name
                    )

                # =================================================
                # UPDATE UNREAD COUNT
                # =================================================

                conversation.unread_count = (
                    conversation.unread_count or 0
                ) + 1

                # =================================================
                # UPDATE LAST MESSAGE
                # =================================================

                conversation.last_message_at = (
                    datetime.utcnow()
                )

                conversation.last_message_preview = (
                    body
                )

                # =================================================
                # SAVE INBOUND MESSAGE
                # =================================================

                wa_msg = WhatsAppMessage(
                    company_id=config.company_id,
                    conversation_id=conversation.id,
                    customer_id=customer.id,
                    direction=MessageDirection.INBOUND,
                    status=MessageStatus.RECEIVED,
                    message_type=msg_type,
                    body=body,
                    wa_message_id=msg_id,
                    ai_generated=False,
                )

                db.add(wa_msg)

                db.commit()

                db.refresh(wa_msg)

                logger.info(
                    "📌 SAVED INBOUND MESSAGE "
                    "id=%s wa_id=%s conversation_id=%s "
                    "phone=%s body=%r",
                    wa_msg.id,
                    msg_id,
                    conversation.id,
                    conversation.customer_phone,
                    body,
                )

                results.append(
                    {
                        "status": "processed",
                        "message_id": wa_msg.id,
                        "wa_message_id": msg_id,
                        "conversation_id": (
                            conversation.id
                        ),
                        "customer_id": customer.id,
                        "phone": (
                            normalized_from_phone
                        ),
                        "body": body,
                    }
                )

                # =================================================
                # 3. AI AUTO REPLY
                # =================================================

                if config.auto_reply_enabled:

                    try:

                        # -----------------------------------------
                        # Get recent history
                        # -----------------------------------------

                        history_msgs = (
                            db.query(
                                WhatsAppMessage
                            )
                            .filter(
                                WhatsAppMessage.conversation_id
                                == conversation.id
                            )
                            .order_by(
                                WhatsAppMessage.created_at.desc()
                            )
                            .limit(6)
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
                                "text": (
                                    m.body or ""
                                ),
                            }
                            for m in reversed(
                                history_msgs
                            )
                        ]

                        # -----------------------------------------
                        # Generate AI reply
                        # -----------------------------------------

                        reply_text = (
                            generate_whatsapp_ai_reply(
                                db=db,
                                company_id=config.company_id,
                                customer_phone=(
                                    normalized_from_phone
                                ),
                                incoming_text=body,
                                conversation_history=(
                                    formatted_history
                                ),
                                custom_instructions=(
                                    config.ai_instructions
                                ),
                            )
                        )

                        logger.info(
                            "🤖 AI reply generated "
                            "conversation_id=%s",
                            conversation.id,
                        )

                        # -----------------------------------------
                        # Send AI reply
                        # -----------------------------------------

                        send_res = (
                            send_meta_whatsapp_message(
                                phone_number_id=(
                                    config.phone_number_id
                                    or ""
                                ),
                                access_token=(
                                    config.access_token
                                    or ""
                                ),
                                recipient_phone=(
                                    normalized_from_phone
                                ),
                                message_text=reply_text,
                            )
                        )

                        # -----------------------------------------
                        # Determine status
                        # -----------------------------------------

                        outbound_status = (
                            MessageStatus.SENT
                            if send_res.get(
                                "status"
                            )
                            in [
                                "sent",
                                "simulated",
                            ]
                            else MessageStatus.FAILED
                        )

                        # -----------------------------------------
                        # Save AI outbound message
                        # -----------------------------------------

                        outbound_msg = (
                            WhatsAppMessage(
                                company_id=(
                                    config.company_id
                                ),
                                conversation_id=(
                                    conversation.id
                                ),
                                customer_id=(
                                    customer.id
                                ),
                                direction=(
                                    MessageDirection.OUTBOUND
                                ),
                                status=(
                                    outbound_status
                                ),
                                message_type="text",
                                body=reply_text,
                                wa_message_id=(
                                    send_res.get(
                                        "wa_message_id"
                                    )
                                ),
                                ai_generated=True,
                            )
                        )

                        db.add(
                            outbound_msg
                        )

                        conversation.last_message_at = (
                            datetime.utcnow()
                        )

                        conversation.last_message_preview = (
                            reply_text
                        )

                        db.commit()

                        db.refresh(
                            outbound_msg
                        )

                        logger.info(
                            "🤖 AI AUTO REPLY SAVED "
                            "message_id=%s "
                            "status=%s",
                            outbound_msg.id,
                            outbound_status.value,
                        )

                        results.append(
                            {
                                "status": (
                                    "auto_reply_sent"
                                    if outbound_status
                                    == MessageStatus.SENT
                                    else "auto_reply_failed"
                                ),
                                "message_id": (
                                    outbound_msg.id
                                ),
                                "wa_message_id": (
                                    outbound_msg.wa_message_id
                                ),
                                "body": reply_text,
                                "error": send_res.get(
                                    "error"
                                ),
                            }
                        )

                    except Exception:

                        logger.exception(
                            "❌ Error generating/sending "
                            "WhatsApp AI auto reply"
                        )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    logger.info(
        "✅ Finished processing WhatsApp webhook "
        "processed_count=%s",
        len(results),
    )

    return {
        "processed_count": len(results),
        "details": results,
    }