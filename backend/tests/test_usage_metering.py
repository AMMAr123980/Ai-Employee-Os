"""
Plan quotas.

The behaviour that matters: a Basic company can't make its 501st AI request, a
failed call gives the unit back, and a billing oddity never locks a paying
customer out of their own data.
"""
import pytest

from app import models
from app import usage_metering as metering


def test_basic_plan_blocks_past_the_allowance(db, company):
    limit = metering.PLAN_LIMITS["basic"][metering.AI_REQUESTS]
    metering.consume(db, company.id, metering.AI_REQUESTS, limit)

    with pytest.raises(metering.QuotaExceeded) as exc:
        metering.consume(db, company.id, metering.AI_REQUESTS, 1)
    assert exc.value.metric == metering.AI_REQUESTS
    assert exc.value.plan == "basic"


def test_release_returns_a_reserved_unit(db, company):
    metering.consume(db, company.id, metering.AI_REQUESTS, 5)
    metering.release(db, company.id, metering.AI_REQUESTS, 2)
    assert metering.current_usage(db, company.id, metering.AI_REQUESTS) == 3


def test_release_cannot_manufacture_free_quota(db, company):
    metering.consume(db, company.id, metering.AI_REQUESTS, 1)
    metering.release(db, company.id, metering.AI_REQUESTS, 50)
    assert metering.current_usage(db, company.id, metering.AI_REQUESTS) == 0


def test_check_does_not_increment(db, company):
    metering.check(db, company.id, metering.AI_REQUESTS, 10)
    assert metering.current_usage(db, company.id, metering.AI_REQUESTS) == 0


def test_business_plan_is_unlimited_for_requests_but_not_storage(db, company):
    company.plan = models.Plan.BUSINESS
    db.commit()
    metering.consume(db, company.id, metering.AI_REQUESTS, 50_000)  # no exception
    assert metering.limit_for("business", metering.AI_REQUESTS) is None
    assert metering.limit_for("business", metering.STORAGE_BYTES) is not None


def test_storage_is_lifetime_and_requests_are_monthly():
    assert metering._period(metering.STORAGE_BYTES) == "lifetime"
    assert metering._period(metering.AI_REQUESTS) != "lifetime"


def test_snapshot_reports_percentages_for_capped_metrics(db, company):
    metering.consume(db, company.id, metering.AI_REQUESTS, 250)
    snapshot = metering.usage_snapshot(db, company.id)
    assert snapshot["plan"] == "basic"
    assert snapshot["metrics"][metering.AI_REQUESTS]["percent"] == 50.0
    assert snapshot["metrics"][metering.AI_REQUESTS]["unlimited"] is False
