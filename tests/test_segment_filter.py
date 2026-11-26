"""Tag (segment) filter for broadcast audience and the stats dropdown."""

import unittest
from unittest.mock import MagicMock, patch

from qlink_chatbot.database import leads as leads_mod
from qlink_chatbot.database.leads import build_lead_query

TAG = "Collated Leads (WhatsApp broadcast PDF)"


class SegmentQueryTest(unittest.TestCase):
    def test_segment_is_array_contains_match(self):
        q = build_lead_query(category="all_leads", segment=TAG)
        self.assertEqual(q, {"segments": TAG})

    def test_no_segment_leaves_query_unchanged(self):
        q = build_lead_query(category="all_leads", whatsapp_ready_only=True)
        self.assertNotIn("segments", q)

    def test_combines_with_source_product_and_sendable_guards(self):
        q = build_lead_query(
            category="all_leads",
            sub_category="Coaching",
            source="Website",
            segment=TAG,
            whatsapp_ready_only=True,
        )
        self.assertEqual(q["segments"], TAG)
        self.assertEqual(q["products"], "Coaching")
        self.assertIn("source", q)
        self.assertIs(q["whatsapp_ready"], True)
        self.assertEqual(q["wrong_number"], {"$ne": True})

    def test_survives_quiz_and_wrapping(self):
        q = build_lead_query(category="quiz_filled", segment=TAG)
        self.assertIn("$and", q)
        self.assertEqual(q["$and"][0], {"segments": TAG})


class SegmentStatsTest(unittest.TestCase):
    def test_stats_return_segments_biggest_first(self):
        facet = {
            "segments": [
                {"_id": "Dubai", "n": 5},
                {"_id": TAG, "n": 680},
                {"_id": None, "n": 2},
            ]
        }
        fake = MagicMock()
        fake.aggregate.return_value = [facet]
        with patch.object(leads_mod, "leads", fake), patch(
            "qlink_chatbot.database.masterclasses.get_active_masterclass",
            return_value=None,
        ):
            stats = leads_mod.get_lead_stats()
        self.assertEqual(list(stats["segments"]), [TAG, "Dubai"])
        self.assertEqual(stats["segments"][TAG], 680)
        stage = fake.aggregate.call_args.args[0][0]["$facet"]["segments"]
        self.assertEqual(stage[0]["$unwind"]["path"], "$segments")


if __name__ == "__main__":
    unittest.main()
