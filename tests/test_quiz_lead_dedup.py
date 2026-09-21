"""Unit tests for quiz lead phone deduplication and re-engagement."""

import unittest
from unittest.mock import MagicMock, patch

from qlink_chatbot.utils.phone import phone_lookup_variants


class PhoneLookupVariantsTest(unittest.TestCase):
    def test_india_10_and_91_variants(self):
        variants = phone_lookup_variants("919876543210")
        self.assertIn("919876543210", variants)
        self.assertIn("9876543210", variants)

    def test_10_digit_adds_91(self):
        variants = phone_lookup_variants("9876543210")
        self.assertIn("9876543210", variants)
        self.assertIn("919876543210", variants)


class UpsertQuizLeadDedupTest(unittest.TestCase):
    @patch("qlink_chatbot.database.leads.get_lead_by_id")
    @patch("qlink_chatbot.database.leads.leads")
    def test_resubmit_with_country_code_updates_same_lead(
        self, mock_leads, mock_get_lead_by_id
    ):
        from qlink_chatbot.database.leads import upsert_quiz_lead

        existing = {
            "lead_id": "lead-1",
            "contact_number": "9876543210",
            "contact_numbers": ["9876543210"],
        }
        mock_leads.find_one.return_value = existing
        mock_get_lead_by_id.return_value = {**existing, "engagement": []}

        upsert_quiz_lead(
            "Yatri",
            "919876543210",
            "y@example.com",
            "Guard",
            {"q1": "a"},
        )

        mock_leads.insert_one.assert_not_called()
        mock_leads.update_one.assert_called_once()
        update = mock_leads.update_one.call_args[0][1]
        self.assertEqual(update["$push"]["engagement"]["type"], "quiz_reengaged")
        self.assertEqual(mock_leads.update_one.call_args[0][0], {"lead_id": "lead-1"})
        self.assertEqual(
            update["$set"]["contact_number"],
            "919876543210",
        )

    @patch("qlink_chatbot.database.leads.get_lead_by_id")
    @patch("qlink_chatbot.database.leads.leads")
    def test_first_submit_creates_quiz_submitted_event(
        self, mock_leads, mock_get_lead_by_id
    ):
        from qlink_chatbot.database.leads import upsert_quiz_lead

        mock_leads.find_one.return_value = None
        mock_get_lead_by_id.return_value = {"lead_id": "new-lead"}

        upsert_quiz_lead("Yatri", "9876543210", None, "Guard", {})

        mock_leads.insert_one.assert_called_once()
        inserted = mock_leads.insert_one.call_args[0][0]
        self.assertEqual(inserted["engagement"][0]["type"], "quiz_submitted")
        mock_leads.update_one.assert_not_called()


if __name__ == "__main__":
    unittest.main()
