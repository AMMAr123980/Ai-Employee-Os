from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_role, hash_password

router = APIRouter(prefix="/api/team", tags=["team"])


@router.get("", response_model=list[schemas.TeamMemberOut])
def list_team(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Any authenticated team member can see the roster — only inviting, role
    changes, and removal are restricted (see below)."""
    return (
        db.query(models.User)
        .filter(models.User.company_id == current_user.company_id)
        .order_by(models.User.created_at.asc())
        .all()
    )


@router.post("/invite", response_model=schemas.TeamMemberOut)
def invite_member(
    payload: schemas.TeamInviteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.OWNER, models.UserRole.ADMIN)),
):
    from app import usage_metering
    try:
        usage_metering.check(db, current_user.company_id, usage_metering.USER_SEATS)
    except usage_metering.QuotaExceeded as exc:
        raise HTTPException(402, detail=str(exc))

    if payload.role == models.UserRole.OWNER and current_user.role != models.UserRole.OWNER:
        raise HTTPException(403, "Only an owner can grant the owner role")

    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(400, "An account with this email already exists")

    member = models.User(
        company_id=current_user.company_id,
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(member)
    db.commit()
    usage_metering.consume(db, current_user.company_id, usage_metering.USER_SEATS)
    db.refresh(member)
    return member


@router.patch("/{user_id}/role", response_model=schemas.TeamMemberOut)
def update_role(
    user_id: str,
    payload: schemas.RoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.OWNER)),
):
    member = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.company_id == current_user.company_id)
        .first()
    )
    if not member:
        raise HTTPException(404, "Team member not found")

    if member.id == current_user.id and payload.role != models.UserRole.OWNER:
        # Prevent the last owner from accidentally demoting themselves with no
        # one left to promote anyone back — simplest safe rule: an owner can only
        # change their own role if at least one other owner exists.
        other_owners = (
            db.query(models.User)
            .filter(
                models.User.company_id == current_user.company_id,
                models.User.role == models.UserRole.OWNER,
                models.User.id != current_user.id,
            )
            .count()
        )
        if other_owners == 0:
            raise HTTPException(400, "You're the only owner — promote someone else to owner first")

    member.role = payload.role
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{user_id}")
def remove_member(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.UserRole.OWNER)),
):
    if user_id == current_user.id:
        raise HTTPException(400, "You can't remove yourself. Ask another owner to do it.")

    member = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.company_id == current_user.company_id)
        .first()
    )
    if not member:
        raise HTTPException(404, "Team member not found")

    if member.role == models.UserRole.OWNER:
        other_owners = (
            db.query(models.User)
            .filter(
                models.User.company_id == current_user.company_id,
                models.User.role == models.UserRole.OWNER,
                models.User.id != member.id,
            )
            .count()
        )
        if other_owners == 0:
            raise HTTPException(400, "Can't remove the only owner")

    db.delete(member)
    db.commit()
    return {"ok": True}
