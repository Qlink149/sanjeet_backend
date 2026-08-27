"""Unit tests for campaign delivery-status helpers."""

import unittest

from qlink_chatbot.utils.campaign_status import (
    extract_message_event_ids,
    extract_status_lookup_ids,
    should_apply_status,
)


class ExtractStatusLookupIdsTest(unittest.TestCase):
    """Passthrough V3 status object id extraction."""

    def test_prefers_gs_id_over_whatsapp_id(self):
        """Prefer Gupshup gs_id over WhatsApp id for lookup."""
        primary, wa = extract_status_lookup_ids(
            {
                "id": "wa-message-id",
                "gs_id": "gupshup-message-id",
                "status": "delivered",
            }
        )
        self.assertEqual(primary, "gupshup-message-id")
        self.assertEqual(wa, "wa-message-id")

    def test_gsId_camel_case(self):
        """Accept camelCase gsId from some webhook payloads."""
        primary, wa = extract_status_lookup_ids(
            {"id": "wa-id", "gsId": "gs-id", "status": "read"}
        )
        self.assertEqual(primary, "gs-id")
        self.assertEqual(wa, "wa-id")

    def test_falls_back_to_id_when_gs_id_missing(self):
        """Fall back to id when gs_id is absent."""
        primary, wa = extract_status_lookup_ids(
            {"id": "only-wa-or-legacy", "status": "sent"}
        )
        self.assertEqual(primary, "only-wa-or-legacy")
        self.assertIsNone(wa)

    def test_empty_object(self):
        """Return None ids for an empty status object."""
        primary, wa = extract_status_lookup_ids({})
        self.assertIsNone(primary)
        self.assertIsNone(wa)


class ExtractMessageEventIdsTest(unittest.TestCase):
    """Native message-event payload id extraction."""

    def test_uses_id_as_gupshup_id(self):
        """Treat payload id as the Gupshup id in native format."""
        primary, wa = extract_message_event_ids(
            {"id": "gs-from-id", "type": "delivered"}
        )
        self.assertEqual(primary, "gs-from-id")
        self.assertIsNone(wa)

    def test_prefers_explicit_gs_id(self):
        """Prefer explicit gs_id when both ids are present."""
        primary, wa = extract_message_event_ids(
            {"id": "maybe-wa", "gs_id": "real-gs", "type": "read"}
        )
        self.assertEqual(primary, "real-gs")
        self.assertEqual(wa, "maybe-wa")


class ShouldApplyStatusTest(unittest.TestCase):
    """Status rank / no-downgrade rules."""

    def test_allows_forward_progress(self):
        """Allow status to move forward through the delivery funnel."""
        self.assertTrue(should_apply_status("sent", "delivered"))
        self.assertTrue(should_apply_status("delivered", "read"))
        self.assertTrue(should_apply_status("pending", "sent"))

    def test_blocks_downgrade(self):
        """Reject status downgrades from later to earlier states."""
        self.assertFalse(should_apply_status("read", "delivered"))
        self.assertFalse(should_apply_status("delivered", "sent"))
        self.assertFalse(should_apply_status("sent", "enqueued"))

    def test_allows_same_rank(self):
        """Allow idempotent updates of the same status."""
        self.assertTrue(should_apply_status("sent", "sent"))

    def test_failed_is_terminal(self):
        """Do not overwrite failed or undelivered statuses."""
        self.assertFalse(should_apply_status("failed", "delivered"))
        self.assertFalse(should_apply_status("undelivered", "sent"))

    def test_can_move_to_failed(self):
        """Allow transition into failed or undelivered."""
        self.assertTrue(should_apply_status("sent", "failed"))
        self.assertTrue(should_apply_status("enqueued", "undelivered"))

    def test_rejects_empty_new_status(self):
        """Reject empty new status values."""
        self.assertFalse(should_apply_status("sent", ""))


if __name__ == "__main__":
    unittest.main()
