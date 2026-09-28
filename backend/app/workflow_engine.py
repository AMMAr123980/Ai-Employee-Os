import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models import Customer, Invoice, Quotation, EmailMessage, EmailStatus, CustomerNote, NoteType, PipelineStage
from app.task_models import Task, TaskStatus, TaskPriority, TaskSource
from app.workflow_models import Workflow, WorkflowStep, WorkflowRun, WorkflowRunStep, WorkflowRunStatus, WorkflowStepStatus
from app.pdf_generator import generate_receipt_pdf
from app.email_sender import send_email as send_smtp_email
from app.whatsapp_assistant import send_meta_whatsapp_message
from app.whatsapp_models import WhatsAppAccountConfig

logger = logging.getLogger("workflow_engine")


def execute_workflow_step(
    db: Session,
    company_id: str,
    step: WorkflowStep,
    payload: Dict[str, Any],
    accumulated_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Executes a single workflow step and returns step output dict."""
    config = json.loads(step.config_json) if step.config_json else {}
    action_type = step.action_type

    invoice_id = payload.get("invoice_id")
    customer_id = payload.get("customer_id")
    
    # Auto-resolve customer if only invoice_id is present
    invoice = None
    if invoice_id:
        invoice = db.query(Invoice).filter(Invoice.company_id == company_id, Invoice.id == invoice_id).first()
        if invoice and not customer_id:
            customer_id = invoice.customer_id

    customer = None
    if customer_id:
        customer = db.query(Customer).filter(Customer.company_id == company_id, Customer.id == customer_id).first()

    if action_type == "generate_receipt":
        if not invoice or not customer:
            raise ValueError("generate_receipt step requires valid invoice_id and customer")
        
        payment_amount = payload.get("amount", invoice.amount_paid or invoice.total)
        receipt_bytes = generate_receipt_pdf(invoice, customer, payment_amount=payment_amount)
        
        return {
            "status": "receipt_generated",
            "invoice_number": invoice.number,
            "customer_name": customer.name,
            "amount": payment_amount,
            "receipt_bytes_len": len(receipt_bytes),
        }

    elif action_type == "update_crm_stage":
        if not customer:
            raise ValueError("update_crm_stage step requires a valid customer")

        target_stage_str = config.get("stage", "won").lower()
        stage_enum = None
        for s in PipelineStage:
            if s.value == target_stage_str:
                stage_enum = s
                break
        
        if not stage_enum:
            stage_enum = PipelineStage.WON

        old_stage = customer.pipeline_stage.value
        customer.pipeline_stage = stage_enum

        # Log pipeline change note
        note = CustomerNote(
            company_id=company_id,
            customer_id=customer.id,
            user_id=payload.get("user_id", "system_workflow"),
            note_type=NoteType.STATUS_CHANGE,
            content=f"Workflow '{step.workflow.name if step.workflow else 'Automation'}' changed stage from {old_stage} to {stage_enum.value}"
        )
        db.add(note)
        db.commit()

        return {
            "status": "crm_stage_updated",
            "customer_id": customer.id,
            "customer_name": customer.name,
            "old_stage": old_stage,
            "new_stage": stage_enum.value,
        }

    elif action_type == "send_email":
        if not customer or not customer.email:
            logger.warning(f"send_email step skipped: no email found for customer {customer_id}")
            return {"status": "skipped", "reason": "No customer email available"}

        subject_tpl = config.get("subject", "Payment Receipt & Order Confirmation")
        body_tpl = config.get("body", "Dear {customer_name},\n\nThank you for your payment. Attached is your official payment receipt.\n\nBest regards,\n{company_name}")
        
        subject = subject_tpl.format(customer_name=customer.name, invoice_number=invoice.number if invoice else "")
        body = body_tpl.format(customer_name=customer.name, invoice_number=invoice.number if invoice else "", company_name=customer.company or "Our Team")

        # Generate receipt PDF attachment if available
        attachment_bytes = None
        attachment_filename = None
        if invoice:
            payment_amount = payload.get("amount", invoice.amount_paid or invoice.total)
            attachment_bytes = generate_receipt_pdf(invoice, customer, payment_amount=payment_amount)
            attachment_filename = f"Receipt_INV_{invoice.number}.pdf"

        # Log outbound email
        email_msg = EmailMessage(
            company_id=company_id,
            user_id=payload.get("user_id", "system_workflow"),
            customer_id=customer.id,
            invoice_id=invoice.id if invoice else None,
            to_email=customer.email,
            subject=subject,
            body=body,
            status=EmailStatus.DRAFT,
            auto_generated=True,
        )
        db.add(email_msg)
        db.commit()

        # Attempt SMTP send if SMTP is configured
        sent_ok = send_smtp_email(
            to_email=customer.email,
            subject=subject,
            body=body,
            attachment_bytes=attachment_bytes,
            attachment_filename=attachment_filename
        )

        email_msg.status = EmailStatus.SENT if sent_ok else EmailStatus.FAILED
        if not sent_ok:
            email_msg.error_message = "SMTP not configured or sending failed — draft saved."
        db.commit()

        return {
            "status": "email_processed",
            "email_id": email_msg.id,
            "sent_ok": sent_ok,
            "recipient": customer.email,
        }

    elif action_type == "send_whatsapp":
        if not customer or not customer.phone:
            logger.warning(f"send_whatsapp step skipped: no phone number for customer {customer_id}")
            return {"status": "skipped", "reason": "No customer phone available"}

        wa_config = db.query(WhatsAppAccountConfig).filter(WhatsAppAccountConfig.company_id == company_id).first()
        phone_id = wa_config.phone_number_id if wa_config else ""
        token = wa_config.access_token if wa_config else ""

        msg_tpl = config.get("message", "Hi {customer_name}, your payment of {amount} has been received. Thank you!")
        msg_text = msg_tpl.format(
            customer_name=customer.name,
            amount=f"{invoice.currency} {payload.get('amount', invoice.amount_paid):,.2f}" if invoice else "your account",
            invoice_number=invoice.number if invoice else ""
        )

        res = send_meta_whatsapp_message(
            phone_number_id=phone_id,
            access_token=token,
            recipient_phone=customer.phone,
            message_text=msg_text
        )

        return {
            "status": "whatsapp_sent",
            "recipient_phone": customer.phone,
            "wa_status": res.get("status"),
            "wa_message_id": res.get("wa_message_id"),
        }

    elif action_type in ["create_notification", "create_task"]:
        task_title = config.get("title", f"Workflow Task: Process order for {customer.name if customer else 'Customer'}")
        task_desc = config.get("description", f"Automated workflow trigger for event '{payload.get('event_type')}'")

        task = Task(
            company_id=company_id,
            customer_id=customer.id if customer else None,
            title=task_title,
            description=task_desc,
            status=TaskStatus.OPEN,
            priority=TaskPriority.HIGH if config.get("priority") == "high" else TaskPriority.NORMAL,
            source=TaskSource.AI_EMPLOYEE,
            source_ref=step.workflow_id
        )
        db.add(task)
        db.commit()

        return {
            "status": "task_created",
            "task_id": task.id,
            "title": task.title,
        }

    elif action_type == "trigger_ai_employee":
        employee_key = config.get("employee_key", "bookkeeper")
        return {
            "status": "ai_employee_notified",
            "employee_key": employee_key,
            "note": "AI Employee task triggered"
        }

    else:
        logger.warning(f"Unknown action_type '{action_type}' in workflow step {step.id}")
        return {"status": "completed", "action_type": action_type}


def trigger_event(
    db: Session,
    company_id: str,
    event_type: str,
    payload: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Dispatches event to all matching active workflows for company."""
    payload["event_type"] = event_type
    workflows = db.query(Workflow).filter(
        Workflow.company_id == company_id,
        Workflow.trigger_type == event_type,
        Workflow.is_active == True,
    ).all()

    run_results = []

    for wf in workflows:
        run = WorkflowRun(
            company_id=company_id,
            workflow_id=wf.id,
            trigger_event=event_type,
            status=WorkflowRunStatus.RUNNING,
            context_json=json.dumps(payload),
            started_at=datetime.utcnow()
        )
        db.add(run)
        db.commit()

        accumulated_context = {"payload": payload}
        has_error = False
        error_msg = None

        for step in wf.steps:
            run_step = WorkflowRunStep(
                run_id=run.id,
                step_order=step.step_order,
                action_type=step.action_type,
                status=WorkflowStepStatus.PENDING,
            )
            db.add(run_step)
            db.commit()

            try:
                out = execute_workflow_step(db, company_id, step, payload, accumulated_context)
                run_step.status = WorkflowStepStatus.SUCCESS if out.get("status") != "skipped" else WorkflowStepStatus.SKIPPED
                run_step.output_json = json.dumps(out)
                accumulated_context[f"step_{step.step_order}"] = out
            except Exception as exc:
                logger.error(f"Error executing workflow step {step.id} (order {step.step_order}): {exc}")
                run_step.status = WorkflowStepStatus.FAILED
                run_step.error_message = str(exc)
                has_error = True
                error_msg = str(exc)
                db.commit()
                break

            db.commit()

        run.completed_at = datetime.utcnow()
        if has_error:
            run.status = WorkflowRunStatus.PARTIAL_FAILURE if len(wf.steps) > 1 else WorkflowRunStatus.FAILED
            run.error_message = error_msg
        else:
            run.status = WorkflowRunStatus.SUCCESS

        db.commit()
        run_results.append({"workflow_id": wf.id, "run_id": run.id, "status": run.status.value})

    return run_results
