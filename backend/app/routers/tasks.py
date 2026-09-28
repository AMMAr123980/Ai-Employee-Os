"""
Task Manager API.

Tasks arrive from four places — typed in here, spoken into the mic, fired by a
conditional follow-up, or extracted from a meeting — and `source` on each row
says which, so "where did this come from?" always has an answer.

The conditional follow-up queue is exposed here too rather than in its own
router: a pending follow-up is a task that hasn't decided whether it needs to
exist yet, and showing both on one screen is the only way a user can see the
whole of what's coming.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, voice_followups
from app import voice_schemas as schemas
from app.auth import get_current_user
from app.database import get_db
from app.task_models import Task, TaskStatus
from app.voice_models import FollowupStatus, VoiceFollowup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _out(db: Session, task: Task) -> schemas.TaskOut:
    customer = db.get(models.Customer, task.customer_id) if task.customer_id else None
    assignee = db.get(models.User, task.assigned_to_user_id) if task.assigned_to_user_id else None
    return schemas.TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        completed_at=task.completed_at,
        customer_id=task.customer_id,
        customer_name=customer.name if customer else None,
        assigned_to_user_id=task.assigned_to_user_id,
        assignee_name=assignee.name if assignee else None,
        source=task.source,
        created_at=task.created_at,
    )


def _owned(db: Session, user: models.User, task_id: str) -> Task:
    task = (
        db.query(Task)
        .filter(Task.id == task_id, Task.company_id == user.company_id)
        .first()
    )
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.get("", response_model=list[schemas.TaskOut])
def list_tasks(
    status: Optional[TaskStatus] = Query(None),
    mine: bool = Query(False, description="Only tasks assigned to you"),
    customer_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(Task).filter(Task.company_id == current_user.company_id)
    if status:
        query = query.filter(Task.status == status)
    if mine:
        query = query.filter(Task.assigned_to_user_id == current_user.id)
    if customer_id:
        query = query.filter(Task.customer_id == customer_id)

    # Open work first, then by due date with undated tasks last — a list sorted
    # purely by due date buries everything that hasn't been given one.
    rows = query.order_by(Task.status.asc(), Task.due_date.is_(None), Task.due_date.asc()).limit(300).all()
    return [_out(db, t) for t in rows]


@router.post("", response_model=schemas.TaskOut)
def create_task(
    payload: schemas.TaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if payload.customer_id:
        owned = (
            db.query(models.Customer)
            .filter(models.Customer.id == payload.customer_id,
                    models.Customer.company_id == current_user.company_id)
            .first()
        )
        if not owned:
            raise HTTPException(404, "Customer not found")

    task = Task(
        company_id=current_user.company_id,
        created_by_user_id=current_user.id,
        assigned_to_user_id=payload.assigned_to_user_id or current_user.id,
        customer_id=payload.customer_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_date=payload.due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _out(db, task)


@router.patch("/{task_id}", response_model=schemas.TaskOut)
def update_task(
    task_id: str,
    payload: schemas.TaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    task = _owned(db, current_user, task_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    # Completion timestamps are derived from status rather than trusted from the
    # client, so "done" and "completed_at" can't disagree.
    if payload.status == TaskStatus.DONE and task.completed_at is None:
        task.completed_at = datetime.utcnow()
    if payload.status in (TaskStatus.OPEN, TaskStatus.IN_PROGRESS):
        task.completed_at = None

    db.commit()
    db.refresh(task)
    return _out(db, task)


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    task = _owned(db, current_user, task_id)
    db.delete(task)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Conditional follow-ups
# --------------------------------------------------------------------------

@router.get("/followups/pending", response_model=list[schemas.FollowupOut])
def list_followups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Everything waiting on a condition, plus recently resolved ones — a
    follow-up that quietly resolved is worth seeing, because it's the feature
    proving it didn't nag anyone."""
    rows = (
        db.query(VoiceFollowup)
        .filter(VoiceFollowup.company_id == current_user.company_id)
        .order_by(VoiceFollowup.due_at.asc())
        .limit(100)
        .all()
    )
    out = []
    for row in rows:
        customer = db.get(models.Customer, row.customer_id) if row.customer_id else None
        out.append(schemas.FollowupOut(
            id=row.id,
            customer_id=row.customer_id,
            customer_name=customer.name if customer else None,
            condition_type=row.condition_type,
            reminder_title=row.reminder_title,
            due_at=row.due_at,
            status=row.status,
            resolved_reason=row.resolved_reason,
            fired_task_id=row.fired_task_id,
            created_at=row.created_at,
        ))
    return out


@router.post("/followups/check-now")
def check_followups_now(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Run the sweep for this company immediately, instead of waiting for the
    scheduler tick. Same code path the background job uses."""
    return voice_followups.sweep_followups(db, company_id=current_user.company_id)


@router.post("/followups/{followup_id}/cancel", response_model=schemas.FollowupOut)
def cancel_followup(
    followup_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    row = (
        db.query(VoiceFollowup)
        .filter(VoiceFollowup.id == followup_id,
                VoiceFollowup.company_id == current_user.company_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Follow-up not found")
    if row.status != FollowupStatus.WAITING:
        raise HTTPException(400, f"This follow-up is already '{row.status.value}'.")

    row.status = FollowupStatus.CANCELLED
    db.commit()

    customer = db.get(models.Customer, row.customer_id) if row.customer_id else None
    return schemas.FollowupOut(
        id=row.id,
        customer_id=row.customer_id,
        customer_name=customer.name if customer else None,
        condition_type=row.condition_type,
        reminder_title=row.reminder_title,
        due_at=row.due_at,
        status=row.status,
        resolved_reason=row.resolved_reason,
        fired_task_id=row.fired_task_id,
        created_at=row.created_at,
    )
