"""
Multi-step planning — the core of the voice feature.

The model call is stubbed in every test, so what's under test is this module's
handling of the response: splitting a sentence into ordered steps, expanding
shorthand, refusing intents the speaker isn't allowed, and never crashing on a
malformed reply.
"""
import pytest

from app import voice_intent


def test_a_three_part_sentence_becomes_three_steps(planned):
    planned({
        "summary": "Quote Acme, email it, chase in three days.",
        "steps": [
            {"intent": "draft_quotation",
             "config": {"customer_name": "Acme", "items_description": "25 laptops"},
             "summary": "Draft a quotation for Acme for 25 laptops.", "confidence": 0.9},
            {"intent": "email_quotation",
             "config": {"quotation_number": "$prev.quotation_number", "customer_name": "Acme"},
             "summary": "Email it to Acme.", "confidence": 0.85},
            {"intent": "schedule_followup",
             "config": {"customer_name": "Acme", "condition": "no_reply", "wait_days": 3},
             "summary": "Chase in three days if they're silent.", "confidence": 0.8},
        ],
    })

    plan = voice_intent.parse_voice_command("draft a quotation for Acme...")

    assert [s.intent for s in plan.steps] == [
        "draft_quotation", "email_quotation", "schedule_followup"]
    assert plan.is_actionable
    # A plan is only as good as its weakest step.
    assert plan.confidence == pytest.approx(0.8)


def test_schedule_meeting_expands_to_a_dated_task(planned):
    planned({"steps": [
        {"intent": "schedule_meeting",
         "config": {"title": "Review", "starts_at": "2026-09-18T15:00"},
         "summary": "Book a review Friday 3pm.", "confidence": 0.9},
    ]})

    plan = voice_intent.parse_voice_command("book a review Friday at 3")
    assert [s.intent for s in plan.steps] == ["create_task"]
    assert plan.steps[0].config["due_at"] == "2026-09-18T15:00"
    assert plan.steps[0].config["title"].startswith("Meeting")


def test_an_intent_the_user_may_not_run_is_not_silently_dropped(planned):
    planned({"steps": [
        {"intent": "send_email", "config": {"customer_name": "Acme"},
         "summary": "Email Acme.", "confidence": 0.9},
    ]})

    plan = voice_intent.parse_voice_command(
        "email Acme", allowed_intents=["create_task", "add_customer_note"])
    # Becomes "unclear" so the user is told, rather than vanishing from a plan
    # they were about to approve.
    assert [s.intent for s in plan.steps] == ["unclear"]
    assert not plan.is_actionable


def test_hallucinated_intent_becomes_unclear(planned):
    planned({"steps": [{"intent": "launch_rocket", "config": {}, "confidence": 0.99}]})
    assert voice_intent.parse_voice_command("do the thing").steps[0].intent == "unclear"


def test_single_step_returned_unwrapped_is_tolerated(planned):
    planned({"steps": {"intent": "create_task", "config": {"title": "Call supplier"},
                       "confidence": 0.9}})
    plan = voice_intent.parse_voice_command("remind me to call the supplier")
    assert [s.intent for s in plan.steps] == ["create_task"]


def test_stray_unclear_steps_are_dropped_from_a_good_plan(planned):
    planned({"steps": [
        {"intent": "create_task", "config": {"title": "X"}, "confidence": 0.9},
        {"intent": "unclear", "config": {}, "confidence": 0.1},
    ]})
    plan = voice_intent.parse_voice_command("remind me, and also mumble")
    assert [s.intent for s in plan.steps] == ["create_task"]


def test_plans_are_capped(planned):
    planned({"steps": [
        {"intent": "create_task", "config": {"title": f"T{i}"}, "confidence": 0.9}
        for i in range(20)
    ]})
    plan = voice_intent.parse_voice_command("a very long sentence")
    assert len(plan.steps) <= voice_intent.MAX_STEPS


def test_model_failure_becomes_a_readable_error(monkeypatch):
    from app import voice_llm

    def _boom(*a, **k):
        raise voice_llm.LLMError("model is down")

    monkeypatch.setattr(voice_llm, "plan_json", _boom)
    with pytest.raises(voice_intent.IntentParsingError):
        voice_intent.parse_voice_command("anything")


def test_prompt_carries_context_timezone_and_language(monkeypatch):
    from app import voice_llm

    captured = {}

    def _capture(system, user, **kwargs):
        captured["system"] = system
        return {"steps": []}

    monkeypatch.setattr(voice_llm, "plan_json", _capture)
    voice_intent.parse_voice_command(
        "email them", context_block="- Customer last discussed: Acme Corp",
        tz_name="Asia/Karachi", locale="ur",
    )
    assert "Acme Corp" in captured["system"]
    assert "Asia/Karachi" in captured["system"]
    assert "Urdu" in captured["system"]
