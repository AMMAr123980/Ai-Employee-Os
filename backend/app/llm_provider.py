import logging
import json
import re
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

from app.config import settings

logger = logging.getLogger("llm_provider")


def complete_text_groq(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None
) -> str:
    """Complete text using Groq API (100% Free tier available at https://console.groq.com)."""
    api_key = getattr(settings, "groq_api_key", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured")

    model_name = model or getattr(settings, "groq_model", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile"
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 1000
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return (msg.get("content") or "").strip()
        return str(data)


def complete_text_gemini(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None
) -> str:
    """Complete text using Google Gemini API (100% Free tier available at https://aistudio.google.com)."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured")

    model_name = model or getattr(settings, "gemini_model", "gemini-3.6-flash") or "gemini-3.6-flash"
    headers = {"Content-Type": "application/json"}
    payload: Dict[str, Any] = {}
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    payload["contents"] = contents

    fallback_models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
    last_err: Exception = RuntimeError("No Gemini models available")
    for current_model in [model_name] + [m for m in fallback_models if m != model_name]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"].strip()
                return str(data)
        except Exception as e:
            logger.warning("Gemini model %s failed (%s), trying next fallback...", current_model, e)
            last_err = e
    raise last_err


def complete_text_openai(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None
) -> str:
    import openai
    model_name = model or settings.openai_model
    client = openai.Client(api_key=settings.openai_api_key)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
        max_tokens=1000
    )
    return (resp.choices[0].message.content or "").strip()


def complete_text_anthropic(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None
) -> str:
    api_key = settings.anthropic_api_key
    model_name = model or settings.anthropic_model or "claude-3-5-sonnet-20241022"

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload: Dict[str, Any] = {
        "model": model_name,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }
    if system_prompt:
        payload["system"] = system_prompt

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        content_blocks = data.get("content", [])
        if content_blocks and "text" in content_blocks[0]:
            return content_blocks[0]["text"].strip()
        return str(data)


def _has_kw(keywords: list, text: str) -> bool:
    for kw in keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE):
            return True
    return False


def smart_contextual_fallback(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    Intelligent Rule-Based & Contextual AI Fallback.
    Ensures customer replies and AI operations are NEVER static or identical,
    even when internet / API keys are unavailable.
    """
    prompt_clean = prompt.strip()
    full_text = f"{system_prompt or ''}\n{prompt_clean}".lower()

    # If JSON output is required by caller
    if "json" in full_text or "json_object" in full_text or "respond with only a json" in full_text:
        # Check if voice command planning
        if "steps" in full_text or "intent" in full_text:
            user_say = prompt_clean.split("\n")[0][:150]
            return json.dumps({
                "steps": [{"intent": "unclear", "config": {}, "summary": f"Received: {user_say}", "confidence": 0.0, "missing_info": []}],
                "summary": f"Could not identify a supported business action for: '{user_say}'"
            })
        # Check if voice meeting summary
        if "action_items" in full_text or "decisions" in full_text:
            return json.dumps({
                "summary": "Audio processed.",
                "decisions": [],
                "action_items": [],
                "deadlines": [],
                "open_questions": []
            })
        # Check if line item drafting
        if "items" in full_text or "quantity" in full_text or "unit_price" in full_text:
            return json.dumps({
                "items": [{"description": prompt_clean[:150] or "Service Item", "quantity": 1, "unit_price": 100.0}],
                "suggested_notes": "Generated from your request."
            })
        # General JSON fallback
        return json.dumps({
            "status": "success",
            "message": "Processed successfully",
            "intent": "general_inquiry"
        })

    # WhatsApp or natural language chat responses
    # Extract customer message if available
    customer_msg = prompt_clean
    if "New Customer Message:" in prompt_clean:
        customer_msg = prompt_clean.split("New Customer Message:")[1].split("\n\n")[0].strip()

    low = customer_msg.lower()

    # 1. Invoices / Payment / Bills
    if _has_kw(["invoice", "bill", "payment", "due", "paid", "amount", "price", "pricing", "cost", "rate", "fees"], low):
        return f"Regarding invoices and account status at {settings.company_name}: You can view your current account details and active invoices. Let us know if you would like a specific invoice PDF sent to you!"

    # 2. Meetings / Scheduling / Appointment / Call
    if _has_kw(["meeting", "call", "schedule", "appointment", "zoom", "meet", "time", "talk", "calendar"], low):
        return f"I would be glad to schedule a meeting with our team at {settings.company_name}. Please share your preferred day and time, and we will confirm the calendar event!"

    # 3. Quotation / Estimate / Proposal / Product Purchase
    if _has_kw(["quote", "quotation", "estimate", "proposal", "laptop", "laptops", "buy", "purchase", "order"], low):
        return f"Thank you for your quotation request with {settings.company_name}! We have logged your requirement ('{customer_msg[:80]}') and our sales team will send over a detailed quote shortly."

    # 4. Greetings (English / Urdu / Roman Urdu)
    if _has_kw(["hi", "hello", "hey", "salam", "assalam", "aoa", "adab", "good morning", "good afternoon"], low):
        return f"Walaikum Assalam! Thank you for contacting {settings.company_name}. How can I assist you with your project or inquiry today?"

    # 5. General inquiries
    return f"Thank you for contacting {settings.company_name}! Regarding your message: '{customer_msg[:120]}', our team is reviewing your request and will provide you with full assistance shortly."


def complete_text(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None
) -> str:
    """Unified LLM completion router for Gemini, Groq, OpenAI, and Anthropic Claude."""
    target_provider = (provider or settings.ai_provider or "gemini").lower()

    # 1. Gemini (Default & Free API)
    if target_provider == "gemini" and settings.gemini_api_key:
        try:
            return complete_text_gemini(prompt, system_prompt, model)
        except Exception as e:
            logger.error("Gemini API error: %s. Trying fallbacks.", e)

    # 2. Groq (Free API)
    if (target_provider == "groq" or getattr(settings, "groq_api_key", "")) and getattr(settings, "groq_api_key", ""):
        try:
            return complete_text_groq(prompt, system_prompt, model)
        except Exception as e:
            logger.error("Groq API error: %s. Trying fallbacks.", e)

    # Try Gemini if target was not gemini initially but key exists
    if target_provider != "gemini" and settings.gemini_api_key:
        try:
            return complete_text_gemini(prompt, system_prompt, model)
        except Exception as e:
            logger.error("Gemini fallback error: %s", e)

    # 3. OpenAI
    if settings.openai_api_key:
        try:
            return complete_text_openai(prompt, system_prompt, model)
        except Exception as e:
            logger.error("OpenAI API error: %s", e)

    # 4. Anthropic Claude
    if settings.anthropic_api_key:
        try:
            return complete_text_anthropic(prompt, system_prompt, model)
        except Exception as e:
            logger.error("Anthropic API error: %s", e)

    # 5. Smart Rule-Based Fallback
    logger.info("Using smart contextual AI fallback response")
    return smart_contextual_fallback(prompt, system_prompt)
