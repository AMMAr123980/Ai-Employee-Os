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


class WorkflowRunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL_FAILURE = "partial_failure"


class WorkflowStepStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    trigger_type = Column(String, nullable=False, index=True)  # e.g. "payment_received", "customer_created"
    is_active = Column(Boolean, default=True, nullable=False)
    is_template = Column(Boolean, default=False, nullable=False)

    config_json = Column(Text, nullable=True)  # conditions or trigger filters

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    steps = relationship("WorkflowStep", back_populates="workflow", order_by="WorkflowStep.step_order", cascade="all, delete-orphan")
    runs = relationship("WorkflowRun", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(String, primary_key=True, default=gen_id)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False, index=True)

    step_order = Column(Integer, default=1, nullable=False)
    name = Column(String, nullable=False)
    action_type = Column(String, nullable=False)  # e.g. "generate_receipt", "update_crm_stage", "send_email", "send_whatsapp"
    config_json = Column(Text, nullable=True)     # action parameters

    created_at = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="steps")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True, default=gen_id)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False, index=True)

    trigger_event = Column(String, nullable=False)
    status = Column(Enum(WorkflowRunStatus), default=WorkflowRunStatus.RUNNING, nullable=False, index=True)
    context_json = Column(Text, nullable=True)  # payload passed in
    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)

    workflow = relationship("Workflow", back_populates="runs")
    step_runs = relationship("WorkflowRunStep", back_populates="run", order_by="WorkflowRunStep.step_order", cascade="all, delete-orphan")


class WorkflowRunStep(Base):
    __tablename__ = "workflow_run_steps"

    id = Column(String, primary_key=True, default=gen_id)
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False, index=True)

    step_order = Column(Integer, nullable=False)
    action_type = Column(String, nullable=False)
    status = Column(Enum(WorkflowStepStatus), default=WorkflowStepStatus.PENDING, nullable=False)

    output_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("WorkflowRun", back_populates="step_runs")
