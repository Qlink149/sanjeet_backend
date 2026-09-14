"""Unit tests for quiz 24h access_yes reminder."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from qlink_chatbot.utils.quiz_access_reminder import (
    is_registered_for_active_masterclass,
    schedule_quiz_access_reminder,
    send_quiz_access_template,
)


class IsRegisteredForActiveMasterclassTest(unittest.TestCase):
    @patch("qlink_chatbot.utils.quiz_access_reminder.get_active_masterclass")
    def test_no_active_masterclass(self, mock_active):
        mock_active.return_value = None
        self.assertFalse(
            is_registered_for_active_masterclass({"masterclass_registrations": []})
        )

    @patch("qlink_chatbot.utils.quiz_access_reminder.get_active_masterclass")
    def test_registered_for_active(self, mock_active):
        mock_active.return_value = {"masterclass_id": "mc-1"}
        lead = {
            "masterclass_registrations": [
                {"masterclass_id": "mc-old"},
                {"masterclass_id": "mc-1"},
            ]
        }
        self.assertTrue(is_registered_for_active_masterclass(lead))

    @patch("qlink_chatbot.utils.quiz_access_reminder.get_active_masterclass")
    def test_only_old_registration(self, mock_active):
        mock_active.return_value = {"masterclass_id": "mc-new"}
        lead = {"masterclass_registrations": [{"masterclass_id": "mc-old"}]}
        self.assertFalse(is_registered_for_active_masterclass(lead))


class ScheduleQuizAccessReminderTest(unittest.TestCase):
    @patch("qlink_chatbot.utils.quiz_access_reminder.leads")
    def test_sets_due_at_24h_later(self, mock_leads):
        sent_at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        schedule_quiz_access_reminder("lead-1", sent_at)
        mock_leads.update_one.assert_called_once()
        fields = mock_leads.update_one.call_args[0][1]["$set"]
        self.assertEqual(fields["quiz_access_first_sent_at"], sent_at)
        self.assertEqual(
            fields["quiz_access_reminder_due_at"],
            sent_at + timedelta(hours=24),
        )


class SendQuizAccessTemplateTest(unittest.TestCase):
    @patch("qlink_chatbot.utils.quiz_access_reminder.schedule_quiz_access_reminder")
    @patch("qlink_chatbot.utils.quiz_access_reminder.append_chat_entries")
    @patch("qlink_chatbot.utils.quiz_access_reminder.send_template_message")
    @patch("qlink_chatbot.utils.quiz_access_reminder.quiz_submit_template_id", "tpl-1")
    def test_initial_success_schedules_reminder(
        self, mock_send, mock_append, mock_schedule
    ):
        mock_send.return_value = {"success": True, "message_id": "m1"}
        send_quiz_access_template("919999999999", "Test", kind="initial", lead_id="l1")
        mock_schedule.assert_called_once()
        self.assertEqual(mock_schedule.call_args[0][0], "l1")

    @patch("qlink_chatbot.utils.quiz_access_reminder.schedule_quiz_access_reminder")
    @patch("qlink_chatbot.utils.quiz_access_reminder.append_chat_entries")
    @patch("qlink_chatbot.utils.quiz_access_reminder.send_template_message")
    @patch("qlink_chatbot.utils.quiz_access_reminder.quiz_submit_template_id", "tpl-1")
    def test_initial_failure_does_not_schedule(
        self, mock_send, mock_append, mock_schedule
    ):
        mock_send.return_value = {"success": False, "error": "fail"}
        send_quiz_access_template("919999999999", "Test", kind="initial", lead_id="l1")
        mock_schedule.assert_not_called()

    @patch("qlink_chatbot.utils.quiz_access_reminder.schedule_quiz_access_reminder")
    @patch("qlink_chatbot.utils.quiz_access_reminder.append_chat_entries")
    @patch("qlink_chatbot.utils.quiz_access_reminder.send_template_message")
    @patch("qlink_chatbot.utils.quiz_access_reminder.quiz_submit_template_id", "tpl-1")
    def test_reminder_does_not_schedule_again(
        self, mock_send, mock_append, mock_schedule
    ):
        mock_send.return_value = {"success": True, "message_id": "m1"}
        send_quiz_access_template("919999999999", "Test", kind="reminder", lead_id="l1")
        mock_schedule.assert_not_called()


if __name__ == "__main__":
    unittest.main()
