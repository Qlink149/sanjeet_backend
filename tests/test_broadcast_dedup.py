"""Tests: nobody gets the same template twice, plus the phone/list fixes."""

import unittest
from unittest.mock import MagicMock, patch

from pymongo.errors import DuplicateKeyError

from qlink_chatbot.utils import broadcast_guard as guard
from qlink_chatbot.utils.phone import (
    first_valid_phone,
    is_valid_wa_phone,
    normalize_phone_list,
    normalize_wa_phone,
    partition_phones,
    split_phone_candidates,
)


class PhoneFixesTest(unittest.TestCase):
    def test_stray_trunk_zero_after_91(self):
        # '9109870777200' is 91 + 0 + 9870777200: the same person as 919870777200
        self.assertEqual(normalize_wa_phone("9109870777200"), "919870777200")
        self.assertEqual(normalize_wa_phone("+9109769900050"), "919769900050")

    def test_existing_formats_unchanged(self):
        self.assertEqual(normalize_wa_phone("9820460643"), "919820460643")
        self.assertEqual(normalize_wa_phone("09820460643"), "919820460643")
        self.assertEqual(normalize_wa_phone("+91 98204 60643"), "919820460643")
        self.assertEqual(normalize_wa_phone("971501234567"), "971501234567")

    def test_two_numbers_in_one_cell_are_split_not_glued(self):
        self.assertEqual(
            split_phone_candidates("8291604497 / 9820144270"),
            ["8291604497", "9820144270"],
        )
        self.assertEqual(first_valid_phone("8291604497/9820144270"), "918291604497")

    def test_indian_number_preferred_over_foreign_in_same_cell(self):
        self.assertEqual(first_valid_phone("61424072291/8897699515"), "918897699515")

    def test_person_with_two_numbers_is_one_recipient(self):
        out = normalize_phone_list(["8291604497/9820144270", "918291604497"])
        self.assertEqual(out, ["918291604497"])

    def test_same_person_in_different_formats_is_one_recipient(self):
        out = normalize_phone_list(
            ["9876543210", "919876543210", "+91 98765 43210", "09876543210", "9109876543210"]
        )
        self.assertEqual(out, ["919876543210"])

    def test_partition_reports_invalid(self):
        valid, invalid = partition_phones(["9876543210", "NA", "123", "932646789"])
        self.assertEqual(valid, ["919876543210"])
        self.assertCountEqual(invalid, ["NA", "123", "932646789"])

    def test_is_valid(self):
        self.assertTrue(is_valid_wa_phone("919876543210"))
        self.assertTrue(is_valid_wa_phone("971501234567"))
        self.assertFalse(is_valid_wa_phone("9198765"))
        self.assertFalse(is_valid_wa_phone("911234567890"))  # 91 + not a mobile
        self.assertFalse(is_valid_wa_phone(""))


class FilterAlreadyReceivedTest(unittest.TestCase):
    @patch.object(guard, "campaigns")
    def test_splits_received_and_new(self, campaigns):
        campaigns.aggregate.return_value = [{"_id": "919800000001"}]
        to_send, skipped = guard.filter_already_received(
            "tpl-1", "coterie_intro", ["919800000001", "919800000002"]
        )
        self.assertEqual(to_send, ["919800000002"])
        self.assertEqual(skipped, ["919800000001"])

    @patch.object(guard, "campaigns")
    def test_only_delivered_states_count_and_template_matches_by_id_or_name(self, campaigns):
        campaigns.aggregate.return_value = []
        guard.filter_already_received("tpl-1", "coterie_intro", ["919800000001"], "c-now")
        pipeline = campaigns.aggregate.call_args[0][0]
        match = pipeline[0]["$match"]
        self.assertEqual(
            match["$or"], [{"template_id": "tpl-1"}, {"template_name": "coterie_intro"}]
        )
        self.assertEqual(match["campaign_id"], {"$ne": "c-now"})
        statuses = pipeline[2]["$match"]["recipients.status"]["$in"]
        self.assertEqual(set(statuses), {"sent", "delivered", "read"})  # not failed

    @patch.object(guard, "campaigns")
    def test_no_phones_or_no_template_is_noop(self, campaigns):
        self.assertEqual(guard.filter_already_received("t", "n", []), ([], []))
        campaigns.aggregate.assert_not_called()


class FakeClaims:
    """Just enough of a collection to exercise the unique-claim logic."""

    def __init__(self):
        self.rows = []

    def create_index(self, *a, **k):
        pass

    def insert_one(self, doc):
        if any(r["phone"] == doc["phone"] and r["template_key"] == doc["template_key"] for r in self.rows):
            raise DuplicateKeyError("dup")
        self.rows.append({"_id": len(self.rows) + 1, **doc})

    def find_one(self, q):
        return next((r for r in self.rows if all(r.get(k) == v for k, v in q.items())), None)

    def update_one(self, q, upd):
        row = self.find_one(q)
        if row:
            row.update(upd["$set"])
        return MagicMock(modified_count=1 if row else 0)

    def delete_one(self, q):
        row = self.find_one(q)
        if row:
            self.rows.remove(row)


class TryClaimTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClaims()
        patcher = patch.object(guard, "claims", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        # the owner's send is live unless a test says otherwise (never hit Mongo)
        status = patch.object(guard, "_recipient_status", return_value="sent")
        status.start()
        self.addCleanup(status.stop)

    def test_first_wins_second_loses(self):
        self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-A"))
        self.assertFalse(guard.try_claim("91980", "t1", "tpl", "camp-B"))

    def test_different_person_or_template_is_independent(self):
        self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-A"))
        self.assertTrue(guard.try_claim("91981", "t1", "tpl", "camp-B"))
        self.assertTrue(guard.try_claim("91980", "t2", "other", "camp-B"))

    def test_same_campaign_may_reclaim(self):
        self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-A"))
        self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-A"))

    def test_release_lets_a_retry_through(self):
        self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-A"))
        guard.release_claim("91980", "t1", "tpl", "camp-A")
        self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-B"))

    def test_claim_of_an_undelivered_send_is_taken_over(self):
        self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-A"))
        with patch.object(guard, "_recipient_status", return_value="undelivered"):
            self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-B"))
        self.assertEqual(self.fake.rows[0]["campaign_id"], "camp-B")

    def test_claim_of_a_delivered_send_is_never_taken_over(self):
        self.assertTrue(guard.try_claim("91980", "t1", "tpl", "camp-A"))
        for status in ("sent", "delivered", "read", "pending", None):
            with patch.object(guard, "_recipient_status", return_value=status):
                self.assertFalse(guard.try_claim("91980", "t1", "tpl", "camp-B"), status)


@patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.append_chat_entries")
@patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch._template_chat_content", return_value="msg")
@patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.set_campaign_recipient_sent")
@patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.send_template_message")
@patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.campaigns")
class SendLoopTest(unittest.TestCase):
    def _run(self, phones, **kw):
        from qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch import (
            send_campaign_messages,
        )

        send_campaign_messages("camp-1", phones, "tpl-1", None, **kw)

    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.release_claim")
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.mark_skipped")
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.try_claim")
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.filter_already_received")
    def test_already_received_and_raced_people_are_not_sent(
        self, flt, claim, skipped, release, campaigns, send, sent_rec, content, chat
    ):
        campaigns.find_one.return_value = {"template_name": "coterie_intro"}
        send.return_value = {"success": True, "message_id": "m1"}
        # 919800000001 got it before; 919800000002 loses the race; 919800000003 is new
        flt.return_value = (["919800000002", "919800000003"], ["919800000001"])
        claim.side_effect = lambda phone, *a: phone != "919800000002"
        self._run(["919800000001", "919800000002", "919800000003"])
        send.assert_called_once()
        self.assertEqual(send.call_args[0][0], "919800000003")
        self.assertCountEqual(
            [c.args[1] for c in skipped.call_args_list],
            ["919800000001", "919800000002"],
        )
        release.assert_not_called()

    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.release_claim")
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.mark_skipped")
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.try_claim", return_value=True)
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.filter_already_received")
    def test_failed_send_gives_the_claim_back(
        self, flt, claim, skipped, release, campaigns, send, sent_rec, content, chat
    ):
        campaigns.find_one.return_value = {"template_name": "coterie_intro"}
        flt.return_value = (["919800000001"], [])
        send.return_value = {"success": False, "message_id": None, "error": "boom"}
        self._run(["919800000001"])
        release.assert_called_once()

    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.release_claim")
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.mark_skipped")
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.try_claim")
    @patch("qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch.filter_already_received")
    def test_deliberate_resend_bypasses_the_guard(
        self, flt, claim, skipped, release, campaigns, send, sent_rec, content, chat
    ):
        campaigns.find_one.return_value = {"template_name": "coterie_intro"}
        send.return_value = {"success": True, "message_id": "m1"}
        self._run(["919800000001"], skip_already_sent=False)
        flt.assert_not_called()
        claim.assert_not_called()
        send.assert_called_once()


class MergedListTest(unittest.TestCase):
    def test_skipped_recipients_do_not_count_in_campaign_stats(self):
        from qlink_chatbot.database.db_utils import _campaign_stats

        stats = _campaign_stats(
            [
                {"status": "delivered"},
                {"status": "sent"},
                {"status": "skipped_duplicate"},
                {"status": "skipped_duplicate"},
            ]
        )
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["delivered"], 1)


if __name__ == "__main__":
    unittest.main()
