"""Broadcast templates with {{n}} variables: never send missing or partial values."""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks

from qlink_chatbot import campaign_scheduler as sched_mod
from qlink_chatbot.database import db_utils
from qlink_chatbot.routes import dashboard_routes as dr
from qlink_chatbot.utils import campaign_params as cp
from qlink_chatbot.utils import campaign_retry as retry_mod
from qlink_chatbot.whatsapp_functions.dashboard import send_campaign_batch as batch
from qlink_chatbot.whatsapp_functions.dashboard import send_template_by_id as sender

THREE = {
    "id": "t3",
    "elementName": "link_message",
    "data": "Hi {{1}}. See you on {{2}} at {{3}}.",
}
ZERO = {"id": "t0", "elementName": "plain", "data": "Hello"}
TEMPLATES = [THREE, ZERO]
SPEC = [{"token": "first_name", "fallback": "there"}, "Saturday", "11 AM"]
PHONE = "919876543210"


def _lead(name):
    return patch.object(cp, "find_lead_by_phone", return_value={"name": name})


class CountTest(unittest.TestCase):
    def test_counts_distinct_placeholders(self):
        self.assertEqual(cp.template_variable_count(THREE), 3)
        self.assertEqual(cp.template_variable_count(ZERO), 0)
        repeated = {"data": "{{1}} and {{ 1 }} then {{2}} | [Yes]"}
        self.assertEqual(cp.template_variable_count(repeated), 2)

    def test_refuses_what_it_cannot_be_sure_of(self):
        for template in (
            {},
            {"data": ""},
            {"data": "Hi {{2}}"},
            {"data": "Hi {{name}}"},
            {"data": "Hi", "containerMeta": json.dumps({"header": "Dear {{1}}"})},
            {
                "data": "Hi",
                "containerMeta": json.dumps(
                    {"buttons": [{"type": "URL", "url": "https://x.test/{{1}}"}]}
                ),
            },
        ):
            with self.assertRaises(cp.TemplateParamsError, msg=template):
                cp.template_variable_count(template)

    def test_unavailable_list_and_unknown_template_are_refused(self):
        with self.assertRaises(cp.TemplateUnavailableError):
            cp.check_template_params([], "t0", [])
        with self.assertRaises(cp.TemplateParamsError):
            cp.check_template_params(TEMPLATES, "missing", [])

    def test_count_must_match_exactly(self):
        for raw in (None, [], SPEC[:2], SPEC + ["extra"]):
            with self.assertRaisesRegex(cp.TemplateParamsError, "needs 3"):
                cp.check_template_params(TEMPLATES, "t3", raw)
        with self.assertRaisesRegex(cp.TemplateParamsError, "needs 0"):
            cp.check_template_params(TEMPLATES, "t0", ["x"])
        self.assertEqual(cp.check_template_params(TEMPLATES, "t0", None)[1], [])


class ValuesTest(unittest.TestCase):
    def test_spec_normalises_tokens_and_is_stable(self):
        spec = cp.normalise_param_spec(
            json.dumps(["{first_name}", {"token": "name", "fallback": "friend"}, " a "])
        )
        self.assertEqual(
            spec,
            [
                {"token": "first_name", "fallback": "there"},
                {"token": "name", "fallback": "friend"},
                "a",
            ],
        )
        self.assertEqual(cp.normalise_param_spec(spec), spec)

    def test_bad_items_are_refused(self):
        for raw in (
            "not json",
            '{"a": 1}',
            [""],
            ["  \n "],
            ["​"],
            [None],
            [5],
            ["{firstname}"],
            ["Hi {first_name}"],
            [{"token": "email"}],
        ):
            with self.assertRaises(cp.TemplateParamsError, msg=raw):
                cp.normalise_param_spec(raw)

    def test_sanitises_to_one_clean_line(self):
        self.assertEqual(cp.sanitise_value("  a\n\nb\tc      d \r\n"), "a b c d")

    def test_names_come_from_the_lead(self):
        spec = cp.normalise_param_spec(["{first_name}", "{name}"])
        with _lead("  priya \n shah "):
            self.assertEqual(cp.resolve_params(spec, PHONE), ["Priya", "priya shah"])

    def test_fallback_when_there_is_no_usable_name(self):
        spec = cp.normalise_param_spec(
            ["{first_name}", {"token": "name", "fallback": "friend"}]
        )
        for lead in (None, {}, {"name": "  "}, {"name": "WhatsApp 3210"}, {"name": "98765"}):
            with patch.object(cp, "find_lead_by_phone", return_value=lead):
                self.assertEqual(cp.resolve_params(spec, PHONE), ["there", "friend"])
        blank = cp.normalise_param_spec([{"token": "first_name", "fallback": " "}])
        self.assertEqual(blank[0]["fallback"], "there")

    def test_literals_need_no_lead_lookup(self):
        with patch.object(cp, "find_lead_by_phone") as find:
            self.assertEqual(cp.resolve_params(["a"], PHONE), ["a"])
        find.assert_not_called()


class PayloadTest(unittest.TestCase):
    def _send(self, **kwargs):
        response = MagicMock(status_code=200)
        response.json.return_value = {"status": "submitted", "messageId": "m1"}
        with patch.object(sender.httpx, "post", return_value=response) as post:
            result = sender.send_template_message(PHONE, "t3", **kwargs)
        return result, post

    def test_params_reach_the_gupshup_payload(self):
        _, post = self._send(params=["Priya", "Saturday", "11 AM"])
        template = json.loads(post.call_args.kwargs["data"]["template"])
        self.assertEqual(template["params"], ["Priya", "Saturday", "11 AM"])

    def test_no_params_payload_is_unchanged(self):
        _, post = self._send()
        self.assertEqual(
            post.call_args.kwargs["data"]["template"],
            json.dumps({"id": "t3", "params": []}),
        )

    def test_empty_value_is_never_posted(self):
        result, post = self._send(params=["Priya", " "])
        self.assertFalse(result["success"])
        post.assert_not_called()


class BatchTest(unittest.TestCase):
    def _run(self, campaign, template_id, templates=TEMPLATES):
        mocks = {
            "campaigns": MagicMock(),
            "get_all_templates": MagicMock(return_value=templates),
            "send_template_message": MagicMock(
                return_value={"success": True, "message_id": "m1"}
            ),
            "set_campaign_recipient_sent": MagicMock(),
            "append_chat_entries": MagicMock(),
        }
        mocks["campaigns"].find_one.return_value = campaign
        with patch.multiple(batch, **mocks), _lead("priya shah"):
            batch.send_campaign_messages(
                "c1", [PHONE], template_id, None, skip_already_sent=False
            )
        return mocks

    def test_uses_the_campaign_params_and_logs_filled_text(self):
        mocks = self._run({"template_params": SPEC}, "t3")
        self.assertEqual(
            mocks["send_template_message"].call_args.kwargs["params"],
            ["Priya", "Saturday", "11 AM"],
        )
        entry = mocks["append_chat_entries"].call_args.args[1][0]
        self.assertIn("Hi Priya. See you on Saturday at 11 AM.", entry["content"])

    def test_zero_variable_campaign_sends_as_before(self):
        mocks = self._run({}, "t0")
        self.assertEqual(mocks["send_template_message"].call_args.kwargs["params"], [])

    def test_mismatch_or_unknown_count_sends_nothing(self):
        for campaign, templates in (
            ({}, TEMPLATES),
            ({"template_params": SPEC[:1]}, TEMPLATES),
            ({"template_params": SPEC}, None),
        ):
            mocks = self._run(campaign, "t3", templates)
            mocks["send_template_message"].assert_not_called()
            call = mocks["set_campaign_recipient_sent"].call_args
            self.assertFalse(call.args[3])
            self.assertTrue(call.kwargs["error"].startswith("Not sent:"))

    def test_only_a_template_outage_is_worth_retrying(self):
        outage = self._run({"template_params": SPEC}, "t3", None)
        mismatch = self._run({}, "t3")
        errors = [
            m["set_campaign_recipient_sent"].call_args.kwargs["error"]
            for m in (outage, mismatch)
        ]
        self.assertEqual(
            [retry_mod.is_retriable_campaign_error(e) for e in errors], [True, False]
        )


class RetryTest(unittest.TestCase):
    def _run(self, params, templates=TEMPLATES):
        mocks = {
            "campaigns": MagicMock(),
            "get_all_templates": MagicMock(return_value=templates),
            "send_template_message": MagicMock(
                return_value={"success": True, "message_id": "m1"}
            ),
            "record_campaign_retry_send": MagicMock(),
            "release_claim": MagicMock(),
            "try_claim": MagicMock(return_value=True),
            "resolve_template_image_url": MagicMock(return_value=None),
            "_template_chat_content": MagicMock(return_value="msg"),
            "append_chat_entries": MagicMock(),
        }
        claimed = {
            "campaign_id": "c1",
            "phone_number": PHONE,
            "template_id": "t3",
            "template_params": params,
        }
        with patch.multiple(retry_mod, **mocks), _lead("priya shah"):
            outcome = retry_mod.retry_campaign_recipient(claimed)
        return outcome, mocks

    def test_retry_uses_the_same_params(self):
        outcome, mocks = self._run(SPEC)
        self.assertTrue(outcome["success"])
        self.assertEqual(
            mocks["send_template_message"].call_args.kwargs["params"],
            ["Priya", "Saturday", "11 AM"],
        )

    def test_mismatch_is_marked_failed_and_not_sent(self):
        outcome, mocks = self._run(None)
        self.assertFalse(outcome["success"])
        mocks["send_template_message"].assert_not_called()
        record = mocks["record_campaign_retry_send"].call_args.kwargs
        self.assertIn("needs 3", record["error"])

    def test_template_outage_defers_without_using_up_the_retry(self):
        _, mocks = self._run(SPEC, templates=None)
        mocks["send_template_message"].assert_not_called()
        mocks["record_campaign_retry_send"].assert_not_called()
        update = mocks["campaigns"].update_one.call_args.args[1]["$set"]
        self.assertFalse(update["recipients.$.retry_in_progress"])
        self.assertNotIn("recipients.$.retry_count", update)

    def test_claim_carries_the_campaign_params(self):
        past = "2000-01-01T00:00:00+00:00"
        fake = MagicMock()
        fake.find_one.return_value = {
            "campaign_id": "c1",
            "template_id": "t3",
            "template_params": SPEC,
            "recipients": [{"phone_number": PHONE, "status": "failed", "retry_at": past}],
        }
        fake.update_one.return_value = MagicMock(modified_count=1)
        with patch.object(retry_mod, "campaigns", fake):
            claimed = retry_mod.claim_due_recipient()
        self.assertEqual(claimed["template_params"], SPEC)
        self.assertEqual(fake.find_one.call_args.args[1]["template_params"], 1)


class SchedulerTest(unittest.TestCase):
    def _run(self, sched, templates=TEMPLATES):
        leads = MagicMock()
        leads.find.return_value = [{"contact_number": PHONE}]
        mocks = {
            "leads": leads,
            "get_all_templates": MagicMock(return_value=templates),
            "filter_already_received": MagicMock(side_effect=lambda *a: (a[2], [])),
            "create_campaign": MagicMock(return_value="c1"),
            "resolve_masterclass_nudge_enabled": MagicMock(return_value=False),
            "resolve_template_image_url": MagicMock(return_value=None),
            "send_campaign_messages": MagicMock(),
            "mark_schedule_run": MagicMock(),
        }
        with patch.multiple(sched_mod, **mocks):
            sched_mod._run_one_schedule(
                {"schedule_id": "s1", "template_id": "t3", **sched}, "2026-11-26"
            )
        return mocks

    def test_params_are_stored_on_the_campaign(self):
        mocks = self._run({"template_params": SPEC})
        self.assertEqual(
            mocks["create_campaign"].call_args.kwargs["template_params"], SPEC
        )
        mocks["send_campaign_messages"].assert_called_once()

    def test_mismatch_marks_the_run_failed(self):
        mocks = self._run({})
        mocks["create_campaign"].assert_not_called()
        mocks["send_campaign_messages"].assert_not_called()
        self.assertIn("needs 3", mocks["mark_schedule_run"].call_args.kwargs["error"])

    def test_template_outage_sends_nothing_and_stays_due(self):
        mocks = self._run({"template_params": SPEC}, templates=None)
        mocks["create_campaign"].assert_not_called()
        mocks["mark_schedule_run"].assert_not_called()


class TriggerRouteTest(unittest.TestCase):
    def _trigger(self, template_id="t3", params=None, templates=TEMPLATES, dry_run=False):
        create = MagicMock()
        with patch.object(dr, "get_all_templates", return_value=templates), patch.object(
            dr, "create_campaign", create
        ), patch.object(
            dr, "filter_already_received", side_effect=lambda *a: (a[2], [])
        ), _lead("priya shah"):
            response = asyncio.run(
                dr.trigger_campaign_v2(
                    request=MagicMock(),
                    background_tasks=BackgroundTasks(),
                    template_id=template_id,
                    file=None,
                    phone_numbers="9876543210",
                    phone_codes="91",
                    category=None,
                    sub_category=None,
                    source=None,
                    segment=None,
                    exclude_phone_numbers=None,
                    dry_run=dry_run,
                    skip_already_sent=True,
                    template_params=params,
                )
            )
        return response.status_code, json.loads(response.body), create

    def test_mismatch_is_a_clear_400_and_creates_nothing(self):
        for params in (None, json.dumps(["only one"])):
            for dry_run in (False, True):
                status, body, create = self._trigger(params=params, dry_run=dry_run)
                self.assertEqual(status, 400)
                self.assertIn("needs 3 variable value(s)", body["message"])
                create.assert_not_called()

    def test_template_outage_is_refused(self):
        status, _, create = self._trigger("t0", templates=None)
        self.assertEqual(status, 503)
        create.assert_not_called()

    def test_dry_run_shows_count_and_sample(self):
        status, body, create = self._trigger(params=json.dumps(SPEC), dry_run=True)
        self.assertEqual(status, 200)
        self.assertEqual(body["variable_count"], 3)
        self.assertEqual(
            body["sample_message"], "Hi Priya. See you on Saturday at 11 AM."
        )
        create.assert_not_called()


class ScheduleRouteTest(unittest.TestCase):
    def setUp(self):
        self.collection = MagicMock()
        self.collection.update_one.return_value = MagicMock(matched_count=1)
        self.collection.find_one.return_value = {"schedule_id": "s1", "template_id": "t3"}
        for patcher in (
            patch.object(db_utils, "campaign_schedules", self.collection),
            patch.object(dr, "get_all_templates", return_value=TEMPLATES),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _create(self, **extra):
        payload = dr.ScheduleCreate(
            template_id="t3", template_name="n", send_time="10:00", **extra
        )
        return asyncio.run(dr.create_schedule_route(payload))

    def test_create_refuses_a_mismatch(self):
        self.assertEqual(self._create().status_code, 400)
        self.assertEqual(self._create(template_params=["a"]).status_code, 400)
        self.collection.insert_one.assert_not_called()

    def test_create_stores_and_lists_params(self):
        self.assertEqual(self._create(template_params=SPEC).status_code, 201)
        stored = self.collection.insert_one.call_args.args[0]
        self.assertEqual(stored["template_params"], SPEC)
        self.collection.find.return_value.sort.return_value = [stored]
        self.assertEqual(db_utils.get_schedules()[0]["template_params"], SPEC)

    def _update(self, **body):
        return asyncio.run(
            dr.update_schedule_route("s1", dr.ScheduleUpdate(**body))
        ).status_code

    def test_update_checks_new_params(self):
        self.assertEqual(self._update(template_params=[]), 400)
        self.collection.update_one.assert_not_called()
        self.assertEqual(self._update(template_params=SPEC), 200)

    def test_stopping_a_schedule_needs_no_template_check(self):
        with patch.object(dr, "get_all_templates", return_value=None):
            self.assertEqual(self._update(enabled=False), 200)


if __name__ == "__main__":
    unittest.main()
