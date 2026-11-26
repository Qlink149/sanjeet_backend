"""Clean source/product filters: grouped for filtering, raw data untouched."""

import re
import unittest

from qlink_chatbot.database.leads import build_lead_query
from qlink_chatbot.database.source_lists import (
    group_product_counts,
    group_source_counts,
    product_condition,
    source_condition,
)

PHONE = "Phone contacts (All Contacts.vcf); Phone contacts (All iCloud Contacts.vcf)"
COACH = "Coaching Payment & Client Database › All Leads; Facebook Ad; Coaching Payment & Client Database 2 › All Leads"
PAID = "Phone contacts (All Contacts.vcf); Coaching Payment & Client Database › Payments; Direct"


def hit(label, raw):
    cond = source_condition(label)
    flags = re.IGNORECASE if cond.get("$options") == "i" else 0
    return bool(re.search(cond["$regex"], raw, flags))


class SourceGroupTest(unittest.TestCase):
    def test_every_variant_falls_in_one_group(self):
        for raw in (COACH, PAID, "Coachee Data › Sheet3"):
            self.assertTrue(hit("Coaching database & leads", raw), raw)
        for raw in ("Insta", "Insta DM", "Instagram Follower (X)", "Old relationship (Y Insta Reach)"):
            self.assertTrue(hit("Instagram", raw), raw)
        for raw in (COACH, "MIT iPhone Ads", "MIT Highend Android", "Aashna FB Leads"):
            self.assertTrue(hit("Paid ads (Facebook / MIT)", raw), raw)

    def test_paying_clients_are_only_the_payments_sheets(self):
        self.assertTrue(hit("Paying clients", PAID))
        self.assertFalse(hit("Paying clients", COACH))

    def test_via_and_via_5x_money_stay_separate(self):
        self.assertTrue(hit("Via", "A; Via; B"))
        self.assertFalse(hit("Via", "Via 5X Money"))
        self.assertTrue(hit("Via 5X Money", "Via 5X Money"))

    def test_direct_matches_a_whole_token_only(self):
        self.assertTrue(hit("Direct", PAID))
        self.assertFalse(hit("Direct", "Directory listing"))

    def test_unknown_value_is_an_exact_match(self):
        self.assertEqual(source_condition("Brand new source"), "Brand new source")

    def test_old_merged_label_still_works(self):
        self.assertTrue(
            hit("Coaching Payment & Client Database (all, merged)", COACH)
        )

    def test_counts_group_and_keep_unknown_sources(self):
        out = group_source_counts({PHONE: 10, COACH: 3, PAID: 2, "Brand new source": 1})
        self.assertEqual(out["Phone contacts"], 12)
        self.assertEqual(out["Coaching database & leads"], 5)
        self.assertEqual(out["Paying clients"], 2)
        self.assertEqual(out["Brand new source"], 1)
        self.assertNotIn(COACH, out)
        self.assertEqual(list(out)[0], "Phone contacts")


class ProductGroupTest(unittest.TestCase):
    def test_variants_merge_and_count_a_lead_once(self):
        out = group_product_counts(
            [(["Masterclass list (MC)", "Masterclass list (BOTH)"], 4), (["Get Unstuck - Bonus"], 2), (["Get Unstuck"], 1)]
        )
        self.assertEqual(out["Masterclass list"], 4)
        self.assertEqual(out["Get Unstuck"], 3)

    def test_notes_and_currency_are_hidden_but_big_new_products_show(self):
        out = group_product_counts(
            [(["INR", "AED", "talks too much"], 7), (["Brand New Programme"], 20), (["Evolve+"], 2), (["Evolve"], 1)]
        )
        self.assertNotIn("INR", out)
        self.assertNotIn("talks too much", out)
        self.assertEqual(out["Brand New Programme"], 20)
        self.assertEqual((out["Evolve+"], out["Evolve"]), (2, 1))

    def test_product_condition(self):
        cond = product_condition("Get Unstuck")
        self.assertTrue(re.search(cond["$regex"], "Get Unstuck - Bonus"))
        self.assertEqual(product_condition("Something else"), "Something else")


class QueryTest(unittest.TestCase):
    def test_groups_combine_with_other_filters_and_safety_rules(self):
        q = build_lead_query(
            category="all_leads", source="Calendly", product="Evolve", whatsapp_ready_only=True
        )
        self.assertIn("$regex", q["source"])
        self.assertIn("$regex", q["products"])
        self.assertEqual(q["wrong_number"], {"$ne": True})


if __name__ == "__main__":
    unittest.main()
