"""Unit tests for unified masterclass Utility reminder coordinator."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from qlink_chatbot.utils.masterclass_utility_reminders import (
    _resolve_collision,
    run_due_masterclass_utility_reminders,
)
from qlink_chatbot.utils.template_buttons import template_has_yes_quick_reply


class TemplateHasYesQuickReplyTest(unittest.TestCase):
    @patch("qlink_chatbot.utils.template_buttons.get_all_templates")
    def test_detects_yes_button(self, mock_templates):
        mock_templates.return_value = [
            {
                "id": "tpl-1",
                "containerMeta": (
                    '{"buttons":[{"type":"QUICK_REPLY","text":"Yes"}]}'
                ),
            }
        ]
        self.assertTrue(template_has_yes_quick_reply("tpl-1"))

    @patch("qlink_chatbot.utils.template_buttons.get_all_templates")
    def test_case_insensitive_yes(self, mock_templates):
        mock_templates.return_value = [
            {
                "id": "tpl-1",
                "containerMeta": (
                    '{"buttons":[{"type":"QUICK_REPLY","text":"YES"}]}'
                ),
            }
        ]
        self.assertTrue(template_has_yes_quick_reply("tpl-1"))

    @patch("qlink_chatbot.utils.template_buttons.get_all_templates")
    def test_url_button_only(self, mock_templates):
        mock_templates.return_value = [
            {
                "id": "tpl-1",
                "containerMeta": (
                    '{"buttons":[{"type":"URL","text":"Open","url":"https://x"}]}'
                ),
            }
        ]
        self.assertFalse(template_has_yes_quick_reply("tpl-1"))


class ResolveCollisionTest(unittest.TestCase):
    def test_quiz_wins_over_broadcast(self):
        now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
        quiz = {
            "kind": "quiz_access",
            "phone": "919999999999",
            "due_at": now,
            "template_id": "quiz-tpl",
            "lead_id": "l1",
        }
        broadcast = {
            "kind": "broadcast",
            "phone": "919999999999",
            "due_at": now - timedelta(hours=1),
            "template_id": "bc-tpl",
            "campaign_id": "c1",
        }
        to_send, to_defer = _resolve_collision([quiz, broadcast], now)
        self.assertEqual(to_send["kind"], "quiz_access")
        self.assertEqual(len(to_defer), 1)
        self.assertEqual(to_defer[0]["kind"], "broadcast")


class RunDueMasterclassUtilityRemindersTest(unittest.TestCase):
    @patch(
        "qlink_chatbot.utils.masterclass_utility_reminders._send_nudge",
        return_value={"success": True},
    )
    @patch("qlink_chatbot.utils.masterclass_utility_reminders._claim_item", return_value=True)
    @patch("qlink_chatbot.utils.masterclass_utility_reminders._collect_due_items")
    @patch(
        "qlink_chatbot.utils.masterclass_utility_reminders.is_registered_for_active_masterclass",
        return_value=False,
    )
    @patch("qlink_chatbot.utils.masterclass_utility_reminders.find_lead_by_phone")
    def test_sends_quiz_only_item(
        self,
        mock_find_lead,
        mock_registered,
        mock_collect,
        mock_claim,
        mock_send,
    ):
        due_at = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
        mock_find_lead.return_value = {"lead_id": "l1"}
        mock_collect.side_effect = [
            {
                "919999999999": [
                    {
                        "kind": "quiz_access",
                        "phone": "919999999999",
                        "due_at": due_at,
                        "template_id": "quiz-tpl",
                        "lead_id": "l1",
                    }
                ]
            },
            {},
        ]
        summary = run_due_masterclass_utility_reminders(limit=1)
        self.assertEqual(summary["sent_ok"], 1)
        self.assertEqual(mock_send.call_args[0][0]["kind"], "quiz_access")

    @patch(
        "qlink_chatbot.utils.masterclass_utility_reminders.clear_pending_masterclass_nudges"
    )
    @patch(
        "qlink_chatbot.utils.masterclass_utility_reminders.is_registered_for_active_masterclass",
        return_value=True,
    )
    @patch("qlink_chatbot.utils.masterclass_utility_reminders.find_lead_by_phone")
    @patch("qlink_chatbot.utils.masterclass_utility_reminders._collect_due_items")
    def test_skips_registered_lead(
        self,
        mock_collect,
        mock_find_lead,
        mock_registered,
        mock_clear,
    ):
        due_at = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
        mock_find_lead.return_value = {"lead_id": "l1"}
        mock_collect.side_effect = [
            {
                "919999999999": [
                    {
                        "kind": "broadcast",
                        "phone": "919999999999",
                        "due_at": due_at,
                        "template_id": "bc-tpl",
                        "campaign_id": "c1",
                    }
                ]
            },
            {},
        ]
        summary = run_due_masterclass_utility_reminders(limit=1)
        self.assertEqual(summary["skipped_registered"], 1)
        mock_clear.assert_called_once_with("919999999999")


class ScheduleCampaignMcNudgeTest(unittest.TestCase):
    @patch("qlink_chatbot.database.db_utils.campaigns")
    def test_sets_mc_nudge_due_at(self, mock_campaigns):
        from qlink_chatbot.database.db_utils import schedule_campaign_mc_nudge

        sent_at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        schedule_campaign_mc_nudge("camp-1", "919999999999", sent_at)
        mock_campaigns.update_many.assert_called_once()
        clear_filters = mock_campaigns.update_many.call_args[1]["array_filters"][0]
        self.assertEqual(clear_filters["r.phone_number"], "919999999999")
        mock_campaigns.update_one.assert_called_once()
        fields = mock_campaigns.update_one.call_args[0][1]["$set"]
        self.assertEqual(fields["recipients.$.mc_nudge_due_at"], sent_at + timedelta(hours=24))

    @patch("qlink_chatbot.database.db_utils.campaigns")
    def test_clears_stale_nudges_on_other_campaigns(self, mock_campaigns):
        from qlink_chatbot.database.db_utils import schedule_campaign_mc_nudge

        sent_at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        schedule_campaign_mc_nudge("camp-new", "919999999999", sent_at)
        stale_query = mock_campaigns.update_many.call_args[0][0]
        self.assertEqual(stale_query["campaign_id"], {"$ne": "camp-new"})


class ResolveBroadcastReminderTemplateTest(unittest.TestCase):
    @patch("qlink_chatbot.utils.template_buttons.get_all_templates")
    def test_prefers_approved_masterclass_link_reminder(self, mock_templates):
        from qlink_chatbot.utils.template_buttons import (
            resolve_broadcast_reminder_template_id,
        )

        mock_templates.return_value = [
            {
                "id": "5f8f530a-1668-4da7-8c49-a9e67c3462ae",
                "status": "APPROVED",
                "elementName": "masterclass_link_reminder",
            },
            {
                "id": "6528f8e7-0ec5-43ee-9fb5-fbba70315611",
                "status": "PENDING",
                "elementName": "masterclass_missing_out_reminder",
            },
        ]
        self.assertEqual(
            resolve_broadcast_reminder_template_id(),
            "5f8f530a-1668-4da7-8c49-a9e67c3462ae",
        )


if __name__ == "__main__":
    unittest.main()
