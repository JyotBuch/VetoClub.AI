"""Tests for silent extraction layer."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from server.agent import context
from server.agent.triggers import is_agent_mentioned, strip_trigger
from server.state import preferences
from server.state import session as session_store


class ExtractionTests(unittest.TestCase):
    """Covers XML parsing, session merging, and trigger helpers."""

    def setUp(self) -> None:
        session_store._sessions.clear()  # type: ignore[attr-defined]
        self.base_msg = {
            "group_id": "group-test",
            "sender": "Alisha",
            "text": "sample message",
            "timestamp": "2024-01-01T00:00:00Z",
        }

    def _run_extract(self, response_text: str, message_override: dict | None = None):
        msg = {**self.base_msg, **(message_override or {})}
        session = session_store.get_or_create(msg["group_id"])
        with patch("server.agent.context.complete", AsyncMock(return_value=response_text)):
            updated = asyncio.run(context.extract_and_merge(msg, session))
        return updated

    def test_valid_dietary_updates_member_and_filters(self) -> None:
        xml = """<extraction><dietary>vegetarian</dietary><cuisine_likes></cuisine_likes><cuisine_dislikes></cuisine_dislikes><location></location><confirmed></confirmed><time></time></extraction>"""
        session = self._run_extract(xml, {"text": "I'm vegetarian today"})

        member = session.members["Alisha"]
        self.assertEqual(member.dietary, ["vegetarian"])
        self.assertEqual(session.dietary_filters, ["vegetarian"])

    def test_cuisine_and_time_updates(self) -> None:
        xml = """<extraction><dietary></dietary><cuisine_likes>italian</cuisine_likes><cuisine_dislikes></cuisine_dislikes><location></location><confirmed></confirmed><time>8pm</time></extraction>"""
        session = self._run_extract(xml, {"text": "Italian works at 8pm"})

        member = session.members["Alisha"]
        self.assertEqual(member.cuisine_likes, ["italian"])
        self.assertEqual(session.time, "8pm")

    def test_confirmed_true_updates_member(self) -> None:
        xml = """<extraction><dietary></dietary><cuisine_likes></cuisine_likes><cuisine_dislikes></cuisine_dislikes><location></location><confirmed>true</confirmed><time></time></extraction>"""
        session = self._run_extract(xml, {"sender": "Nidhi", "text": "Count me in"})

        member = session.members["Nidhi"]
        self.assertTrue(member.confirmed)

    def test_malformed_xml_returns_empty(self) -> None:
        session = self._run_extract("not xml at all")

        self.assertEqual(len(session.members), 0)
        self.assertEqual(context.parse_extraction("not xml at all"), {})

    def test_partial_xml_only_updates_present_fields(self) -> None:
        session = session_store.get_or_create("group-partial")
        preferences.upsert_member(session, "Sam", {"dietary": ["vegan"]})
        message = {"group_id": "group-partial", "sender": "Sam", "text": "Near Riverwalk"}
        xml = """<extraction><dietary></dietary><cuisine_likes></cuisine_likes><cuisine_dislikes></cuisine_dislikes><location>Riverwalk</location><confirmed></confirmed><time></time></extraction>"""
        with patch("server.agent.context.complete", AsyncMock(return_value=xml)):
            updated = asyncio.run(context.extract_and_merge(message, session))

        self.assertEqual(updated.members["Sam"].dietary, ["vegan"])
        self.assertEqual(updated.location_anchor, "Riverwalk")
        self.assertEqual(updated.time, None)

    def test_trigger_detection_and_stripping(self) -> None:
        self.assertTrue(is_agent_mentioned("find us a place @Agent"))
        self.assertFalse(is_agent_mentioned("yeah Italian works"))
        self.assertEqual(strip_trigger("find us a place @Agent please"), "find us a place  please")


if __name__ == "__main__":
    unittest.main()
