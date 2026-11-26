"""Scheduled campaigns honour the tag (segment) filter and never widen."""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from qlink_chatbot import campaign_scheduler as sched_mod
from qlink_chatbot.database import db_utils
from qlink_chatbot.routes import dashboard_routes as dr

TAG = "Collated Leads (WhatsApp broadcast PDF)"
# a template without variables, so the variable check passes
TEMPLATES = [{"id": "t1", "elementName": "n", "data": "Hi"}]


class _Cursor(list):
    def sort(self, *_args):
        return self


class FakeSchedules:
    """Equality-only stand-in; like Mongo, ``None`` also matches a missing field."""

    def __init__(self, docs=()):
        self.docs = [dict(d) for d in docs]

    def _matching(self, query):
        return [d for d in self.docs if all(d.get(k) == v for k, v in query.items())]

    def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, query, _projection=None):
        return _Cursor(dict(d) for d in self._matching(query))

    def find_one(self, query, _projection=None):
        found = self._matching(query)
        return dict(found[0]) if found else None

    def update_one(self, query, update):
        found = self._matching(query)
        if found:
            found[0].update(update["$set"])
        return MagicMock(matched_count=len(found[:1]))


class ScheduleRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSchedules()
        patcher = patch.object(db_utils, "campaign_schedules", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        templates = patch.object(dr, "get_all_templates", return_value=TEMPLATES)
        templates.start()
        self.addCleanup(templates.stop)

    def _create(self, **extra):
        payload = dr.ScheduleCreate(
            template_id="t1", template_name="n", send_time="10:00",
            category="all_leads", **extra,
        )
        response = asyncio.run(dr.create_schedule_route(payload))
        self.assertEqual(response.status_code, 201)
        return json.loads(response.body)["data"]

    def _patch(self, schedule_id, **body):
        response = asyncio.run(
            dr.update_schedule_route(schedule_id, dr.ScheduleUpdate(**body))
        )
        self.assertEqual(response.status_code, 200)
        return db_utils.get_schedules()[0]

    def test_create_list_change_and_clear(self):
        data = self._create(segment=TAG)
        self.assertEqual(data["segment"], TAG)
        sid = data["schedule_id"]
        self.assertEqual(db_utils.get_schedules("t1")[0]["segment"], TAG)

        self.assertEqual(self._patch(sid, segment="Dubai")["segment"], "Dubai")
        # omitted or null leaves the tag alone
        self.assertEqual(self._patch(sid, enabled=False)["segment"], "Dubai")
        self.assertEqual(
            self._patch(sid, segment=None, enabled=True)["segment"], "Dubai"
        )
        self.assertIsNone(self._patch(sid, segment="")["segment"])

    def test_empty_string_is_stored_as_no_segment(self):
        self.assertIsNone(self._create(segment="")["segment"])
        self.assertIsNone(self.fake.docs[0]["segment"])


class DuplicateDetectionTest(unittest.TestCase):
    def _ensure(self, fake, segment):
        with patch.object(db_utils, "campaign_schedules", fake):
            return db_utils.ensure_expiry_schedule(
                "t1", "n", "all_leads", None, 3, None, segment=segment
            )

    def test_segment_distinguishes_schedules(self):
        fake = FakeSchedules()
        plain = self._ensure(fake, None)
        tagged = self._ensure(fake, TAG)
        other = self._ensure(fake, "Dubai")
        self.assertEqual(len({plain, tagged, other}), 3)
        self.assertEqual(self._ensure(fake, TAG), tagged)
        self.assertEqual(self._ensure(fake, ""), plain)

    def test_legacy_schedule_without_field_is_still_reused(self):
        legacy = {
            "schedule_id": "old", "template_id": "t1", "schedule_type": "expiry",
            "enabled": True, "category": "all_leads", "sub_category": None,
            "expiry_offset_days": 3, "expiry_date": None,
        }
        fake = FakeSchedules([legacy])
        self.assertEqual(self._ensure(fake, None), "old")
        self.assertNotEqual(self._ensure(fake, TAG), "old")


class SchedulerSegmentTest(unittest.TestCase):
    def _run(self, sched, build=None):
        leads = MagicMock()
        leads.find.return_value = [{"contact_number": "919876543210"}]
        mocks = {
            "leads": leads,
            "get_all_templates": MagicMock(return_value=TEMPLATES),
            "filter_already_received": MagicMock(side_effect=lambda *a: (a[2], [])),
            "create_campaign": MagicMock(return_value="c1"),
            "resolve_masterclass_nudge_enabled": MagicMock(return_value=False),
            "resolve_template_image_url": MagicMock(return_value=None),
            "send_campaign_messages": MagicMock(),
            "mark_schedule_run": MagicMock(),
        }
        if build:
            mocks["build_lead_query"] = build
        base = {"schedule_id": "s1", "template_id": "t1", "category": "all_leads"}
        with patch.multiple(sched_mod, **mocks):
            sched_mod._run_one_schedule({**base, **sched}, "2026-11-26")
        return mocks

    def test_segment_reaches_the_audience_query(self):
        mocks = self._run({"segment": TAG})
        self.assertEqual(mocks["leads"].find.call_args.args[0]["segments"], TAG)
        mocks["send_campaign_messages"].assert_called_once()

    def test_segment_with_quiz_audience(self):
        mocks = self._run({"segment": TAG, "category": "quiz_filled"})
        query = mocks["leads"].find.call_args.args[0]
        self.assertEqual(query["$and"][0]["segments"], TAG)
        mocks["send_campaign_messages"].assert_called_once()

    def test_legacy_and_empty_segment_are_unfiltered_as_before(self):
        for sched in ({}, {"segment": None}, {"segment": ""}):
            mocks = self._run(sched)
            self.assertEqual(
                mocks["leads"].find.call_args.args[0],
                {
                    "whatsapp_ready": True,
                    "contact_number": {"$nin": [None, ""]},
                    "wrong_number": {"$ne": True},
                },
            )
            mocks["send_campaign_messages"].assert_called_once()

    def test_refuses_to_send_if_segment_is_ignored(self):
        ignoring = MagicMock(return_value={"whatsapp_ready": True})
        for sched, build in (({"segment": TAG}, ignoring), ({"segment": []}, None)):
            with patch.object(sched_mod.logger, "exception") as logged:
                mocks = self._run(sched, build)
            logged.assert_called_once()
            mocks["leads"].find.assert_not_called()
            mocks["send_campaign_messages"].assert_not_called()
            mocks["mark_schedule_run"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
