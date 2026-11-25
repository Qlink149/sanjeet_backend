"""A lead marked wrong_number is never sendable, whatever else rewrites whatsapp_ready."""

import unittest
from unittest.mock import MagicMock, patch

from qlink_chatbot.database import leads as leads_mod
from qlink_chatbot.database.leads import build_lead_query


class WrongNumberExcludedTest(unittest.TestCase):
    def test_broadcast_audience_excludes_wrong_numbers(self):
        q = build_lead_query(category="all_leads", whatsapp_ready_only=True)
        self.assertEqual(q["wrong_number"], {"$ne": True})
        self.assertIs(q["whatsapp_ready"], True)

    def test_other_views_are_not_filtered(self):
        q = build_lead_query(not_whatsapp_ready_only=True)
        self.assertNotIn("wrong_number", q)

    def test_recompute_keeps_wrong_number_not_ready(self):
        doc = {
            "_id": 1,
            "contact_number": "919876543210",
            "contact_numbers": ["919876543210"],
            "whatsapp_ready": False,
            "phone_class": "india_91",
            "wrong_number": True,
        }
        fake = MagicMock()
        fake.find.return_value = [doc]
        with patch.object(leads_mod, "leads", fake):
            leads_mod.recompute_lead_phones()
        sets = [c.args[1]["$set"] for c in fake.update_one.call_args_list]
        # already not-ready, so nothing to rewrite; above all it is never flipped on
        self.assertFalse(any(s.get("whatsapp_ready") for s in sets))

    def test_recompute_turns_a_wrongly_ready_flagged_lead_back_off(self):
        doc = {
            "_id": 3,
            "contact_number": "919876543210",
            "contact_numbers": ["919876543210"],
            "whatsapp_ready": True,  # something flipped it back on
            "phone_class": "india_91",
            "wrong_number": True,
        }
        fake = MagicMock()
        fake.find.return_value = [doc]
        with patch.object(leads_mod, "leads", fake):
            leads_mod.recompute_lead_phones()
        sets = [c.args[1]["$set"] for c in fake.update_one.call_args_list]
        self.assertTrue(sets)
        self.assertTrue(all(s["whatsapp_ready"] is False for s in sets))

    def test_recompute_still_marks_normal_leads_ready(self):
        doc = {
            "_id": 2,
            "contact_number": "919876543210",
            "contact_numbers": ["919876543210"],
            "whatsapp_ready": False,
            "phone_class": "india_91",
        }
        fake = MagicMock()
        fake.find.return_value = [doc]
        with patch.object(leads_mod, "leads", fake):
            leads_mod.recompute_lead_phones()
        sets = [c.args[1]["$set"] for c in fake.update_one.call_args_list]
        self.assertTrue(any(s["whatsapp_ready"] is True for s in sets))


if __name__ == "__main__":
    unittest.main()
