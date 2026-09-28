"""
Role enforcement.
"""
import pytest

from app import models
from app import voice_permissions as perms
from app.voice_models import VoiceRolePermission


def test_owner_may_email_a_customer_but_a_member_may_not(db, user):
    user.role = models.UserRole.OWNER
    assert perms.can(db, user, "send_email")

    user.role = models.UserRole.MEMBER
    assert not perms.can(db, user, "send_email")
    assert not perms.can(db, user, "record_payment")
    assert perms.can(db, user, "create_task")      # they can still do the work
    assert perms.can(db, user, "sales_report")


def test_company_override_can_grant(db, company, user):
    user.role = models.UserRole.MEMBER
    db.add(VoiceRolePermission(company_id=company.id, role="member",
                               permission=perms.SEND_TO_CUSTOMER, allowed=True))
    db.commit()
    assert perms.can(db, user, "send_email")


def test_company_override_can_revoke(db, company, user):
    user.role = models.UserRole.ADMIN
    db.add(VoiceRolePermission(company_id=company.id, role="admin",
                               permission=perms.MANAGE_FINANCE, allowed=False))
    db.commit()
    assert not perms.can(db, user, "record_payment")


def test_require_raises_with_the_details_the_ui_needs(db, user):
    user.role = models.UserRole.MEMBER
    with pytest.raises(perms.PermissionDenied) as exc:
        perms.require(db, user, "send_invoice")
    assert exc.value.intent == "send_invoice"
    assert exc.value.role == "member"


def test_allowed_intents_scopes_the_planning_catalog(db, user):
    from app.voice_intent import INTENT_CATALOG

    user.role = models.UserRole.MEMBER
    allowed = perms.allowed_intents(db, user, list(INTENT_CATALOG))
    assert "draft_quotation" in allowed
    assert "email_quotation" not in allowed
    assert "record_payment" not in allowed


def test_every_registered_action_has_a_permission():
    from app.voice_actions import VOICE_ACTION_REGISTRY

    assert [i for i in VOICE_ACTION_REGISTRY if i not in perms.INTENT_PERMISSIONS] == []
