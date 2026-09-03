from qlink_chatbot.database.database import db
from qlink_chatbot.utils.logger_config import logger

idac = db["users"]
campaigns = db["campaigns"]
leads = db["leads"]
template_images = db["template_images"]
campaign_schedules = db["campaign_schedules"]
masterclasses = db["masterclasses"]


def ensure_indexes():
    """Idempotent indexes for dashboard list/filter and webhook lookups."""
    specs = [
        (idac, [("updated_at", -1)], {"name": "users_updated_at"}),
        (idac, [("phone_number", 1)], {"name": "users_phone_number"}),
        (leads, [("lead_id", 1)], {"name": "leads_lead_id"}),
        (
            leads,
            [
                ("whatsapp_ready", 1),
                ("pipeline", 1),
                ("products", 1),
                ("source", 1),
                ("name", 1),
            ],
            {"name": "leads_filter_sort"},
        ),
        (campaigns, [("campaign_id", 1)], {"name": "campaigns_campaign_id"}),
        (
            campaigns,
            [("recipients.gupshup_message_id", 1)],
            {"name": "campaigns_gs_message_id"},
        ),
        (campaigns, [("created_at", -1)], {"name": "campaigns_created_at"}),
        (
            masterclasses,
            [("masterclass_id", 1)],
            {"name": "masterclasses_id", "unique": True},
        ),
        (masterclasses, [("is_active", -1)], {"name": "masterclasses_active"}),
        (
            leads,
            [("masterclass_registrations.masterclass_id", 1)],
            {"name": "leads_mc_registration_id"},
        ),
    ]
    for collection, keys, kwargs in specs:
        try:
            collection.create_index(keys, **kwargs)
        except Exception as e:
            logger.warning(
                "Could not ensure index",
                extra={"index": kwargs.get("name"), "error": str(e)},
            )
    try:
        from qlink_chatbot.database.db_utils import merge_split_user_threads
        from qlink_chatbot.database.leads import recompute_lead_phones

        merge_split_user_threads()
        recompute_lead_phones()
    except Exception as e:
        logger.warning(
            "Could not merge/recompute phone records",
            extra={"error": str(e)},
        )
