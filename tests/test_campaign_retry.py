"""Unit tests for campaign auto-retry helpers."""

import unittest
from unittest.mock import MagicMock, patch

from qlink_chatbot.utils.campaign_retry import (
    MAX_RETRIES_PER_CRON,
    backfill_recipient_retries,
    claim_due_recipient,
    is_retriable_campaign_error,
    run_due_campaign_retries,
    schedule_recipient_retry,
)


class IsRetriableCampaignErrorTest(unittest.TestCase):
    def test_low_balance_codes(self):
        self.assertTrue(is_retriable_campaign_error("[9999] low balance"))
        self.assertTrue(is_retriable_campaign_error("[1003] Wallet Balance Low"))

    def test_rate_limit(self):
        self.assertTrue(is_retriable_campaign_error("[4001] API Rate Limited"))

    def test_invalid_number_not_retriable(self):
        self.assertFalse(
            is_retriable_campaign_error("[1002] Number Not Exist On WhatsApp")
        )

    def test_empty_not_retriable(self):
        self.assertFalse(is_retriable_campaign_error(None))
        self.assertFalse(is_retriable_campaign_error(""))


class RunDueCampaignRetriesTest(unittest.TestCase):
    @patch("qlink_chatbot.utils.campaign_retry.retry_campaign_recipient")
    @patch("qlink_chatbot.utils.campaign_retry.claim_due_recipient")
    def test_batch_cap(self, mock_claim, mock_retry):
        mock_claim.side_effect = [
            {"campaign_id": "c1", "phone_number": "911", "template_id": "t1"},
            {"campaign_id": "c1", "phone_number": "912", "template_id": "t1"},
            None,
        ]
        mock_retry.return_value = {"success": True}

        summary = run_due_campaign_retries(limit=2)

        self.assertEqual(summary["claimed"], 2)
        self.assertEqual(mock_claim.call_count, 2)
        self.assertLessEqual(summary["claimed"], MAX_RETRIES_PER_CRON)


class ScheduleRecipientRetryTest(unittest.TestCase):
    @patch("qlink_chatbot.utils.campaign_retry.campaigns")
    def test_skips_non_retriable(self, mock_campaigns):
        mock_campaigns.find_one.return_value = {
            "retry_policy": {"enabled": True},
            "recipients": [
                {
                    "phone_number": "911",
                    "status": "failed",
                    "retry_count": 0,
                    "retry_at": None,
                }
            ],
        }
        scheduled = schedule_recipient_retry(
            "cid",
            "911",
            "[1002] Number Not Exist On WhatsApp",
        )
        self.assertFalse(scheduled)
        mock_campaigns.update_one.assert_not_called()


class BackfillRecipientRetriesTest(unittest.TestCase):
    @patch("qlink_chatbot.utils.campaign_retry.campaigns")
    def test_schedules_retriable_failures(self, mock_campaigns):
        mock_campaigns.find.return_value = [
            {
                "campaign_id": "cid",
                "recipients": [
                    {
                        "phone_number": "911",
                        "status": "failed",
                        "error": "[9999] low balance",
                        "retry_count": 0,
                        "retry_at": None,
                    }
                ],
            }
        ]
        result = backfill_recipient_retries("cid")
        self.assertEqual(result["scheduled"], 1)
        mock_campaigns.update_one.assert_called_once()


if __name__ == "__main__":
    unittest.main()
