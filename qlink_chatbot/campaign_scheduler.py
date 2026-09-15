"""Background engine for delayed campaign sends.

A schedule (template + delay of 5 or 7 days + daily time) created via
POST /dashboard/schedules fires once after that delay — no one has to
open the dashboard and click Send. Audience is the chosen lead group,
not membership expiry.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from qlink_chatbot.database.collections import leads
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.database.db_utils import (
    create_campaign,
    get_due_schedules,
    mark_schedule_run,
    sync_expiry_jobs_from_templates,
)
from qlink_chatbot.database.leads import build_lead_query
from qlink_chatbot.utils.phone import normalize_phone_list
from qlink_chatbot.utils.template_buttons import resolve_masterclass_nudge_enabled
from qlink_chatbot.utils.template_image import resolve_template_image_url
from qlink_chatbot.whatsapp_functions.dashboard.get_all_templates import (
    get_all_templates,
)
from qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch import (
    send_campaign_messages,
)

IST = ZoneInfo("Asia/Kolkata")

scheduler = BackgroundScheduler(timezone=str(IST))


def _run_one_schedule(sched: dict, run_date: str):
    schedule_id = sched["schedule_id"]
    template_id = sched["template_id"]
    try:
        query = build_lead_query(
            category=sched.get("category"),
            sub_category=sched.get("sub_category"),
            whatsapp_ready_only=True,
        )
        phones = normalize_phone_list(
            [
                d["contact_number"]
                for d in leads.find(query, {"contact_number": 1, "_id": 0})
                if d.get("contact_number")
            ]
        )

        if not phones:
            mark_schedule_run(schedule_id, None, run_date)
            logger.info(
                "Scheduled campaign had no matching leads today",
                extra={"schedule_id": schedule_id, "template_id": template_id},
            )
            return

        all_templates = get_all_templates() or []
        template_name = next(
            (t["elementName"] for t in all_templates if t.get("id") == template_id),
            sched.get("template_name") or template_id,
        )
        campaign_id = create_campaign(
            template_id,
            template_name,
            phones,
            masterclass_nudge_enabled=resolve_masterclass_nudge_enabled(template_id),
        )

        image_url = resolve_template_image_url(template_id)

        send_campaign_messages(campaign_id, phones, template_id, image_url)

        mark_schedule_run(schedule_id, campaign_id, run_date)
        logger.info(
            "Scheduled campaign fired",
            extra={
                "schedule_id": schedule_id,
                "campaign_id": campaign_id,
                "template_id": template_id,
                "total_recipients": len(phones),
            },
        )
    except Exception as e:
        logger.exception(
            "Error running scheduled campaign",
            extra={"schedule_id": schedule_id, "template_id": template_id, "error": str(e)},
        )


def run_due_schedules():
    """Called on every scheduler tick — fires whichever schedules are due."""
    try:
        sync_expiry_jobs_from_templates()
    except Exception:
        logger.exception("Could not sync expiry jobs from template names")
    now_ist = datetime.now(IST)
    run_date = now_ist.strftime("%Y-%m-%d")
    due = get_due_schedules(now_ist)
    for sched in due:
        _run_one_schedule(sched, run_date)


def start_scheduler():
    try:
        sync_expiry_jobs_from_templates()
    except Exception:
        logger.exception("Could not sync expiry jobs from template names")
    scheduler.add_job(
        run_due_schedules,
        "interval",
        minutes=1,
        id="run_due_schedules",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Campaign scheduler started (checks every 1 minute)")
