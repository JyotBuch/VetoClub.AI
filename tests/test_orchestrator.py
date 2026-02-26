"""Tests for Layer 4 active agent orchestration."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from server.agent import orchestrator
from server.agent.orchestrator import run_agent
from server.agent.session_utils import session_to_xml
from server.main import MessagePayload, webhook
from server.state import preferences
from server.state import session as session_store
from server.state.models import GroupSession


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        session_store._sessions.clear()  # type: ignore[attr-defined]

    def _session_with_members(self) -> GroupSession:
        session = session_store.get_or_create("group-1")
        preferences.upsert_member(session, "Johi", {"venue_confirmed": True, "dietary": ["vegetarian"]})
        preferences.upsert_member(session, "Nidhi", {"venue_confirmed": False})
        return session

    def test_session_to_xml_contains_members_and_can_book_false(self) -> None:
        session = self._session_with_members()
        xml = session_to_xml(session)

        self.assertIn("<name>Johi</name>", xml)
        self.assertIn("<name>Nidhi</name>", xml)
        self.assertIn("<can_book>false</can_book>", xml)

    def test_session_to_xml_can_book_true_when_ready(self) -> None:
        session = self._session_with_members()
        preferences.upsert_member(session, "Nidhi", {"venue_confirmed": True})
        session.selected_venue = {"name": "Spot"}

        xml = session_to_xml(session)
        self.assertIn("<can_book>true</can_book>", xml)

    def test_session_to_xml_handles_empty_members(self) -> None:
        session = GroupSession(group_id="empty")
        xml = session_to_xml(session)
        self.assertIn("<members", xml)

    @patch("server.agent.orchestrator.run_tool_loop", new_callable=AsyncMock)
    @patch("server.agent.orchestrator.resolve_full_state", new_callable=AsyncMock)
    @patch("server.agent.orchestrator.complete", new_callable=AsyncMock)
    def test_run_agent_strips_trigger(self, mock_complete: AsyncMock, mock_resolve: AsyncMock, mock_loop: AsyncMock) -> None:
        mock_complete.return_value = object()
        mock_loop.return_value = ("Reply", self._session_with_members())
        mock_resolve.return_value = self._session_with_members()
        session = self._session_with_members()
        session.message_history.append({"sender": "Johi", "text": "Hello"})

        asyncio.run(run_agent("find us spots @Agent", session))

        called_messages = mock_complete.await_args.kwargs["messages"]
        user_message = called_messages[1]["content"]
        self.assertNotIn("@Agent", user_message)

    @patch("server.agent.orchestrator.run_tool_loop", new_callable=AsyncMock)
    @patch("server.agent.orchestrator.resolve_full_state", new_callable=AsyncMock)
    @patch("server.agent.orchestrator.complete", new_callable=AsyncMock)
    def test_run_agent_returns_reply_text(
        self, mock_complete: AsyncMock, mock_resolve: AsyncMock, mock_loop: AsyncMock
    ) -> None:
        mock_complete.return_value = object()
        mock_loop.return_value = ("Done", self._session_with_members())
        mock_resolve.return_value = self._session_with_members()
        session = self._session_with_members()
        reply = asyncio.run(run_agent("@Agent help", session))
        self.assertEqual(reply, "Done")

    @patch("server.agent.orchestrator.resolve_full_state", new_callable=AsyncMock)
    @patch("server.agent.orchestrator.complete", new_callable=AsyncMock)
    def test_run_agent_handles_exception(self, mock_complete: AsyncMock, mock_resolve: AsyncMock) -> None:
        mock_complete.side_effect = RuntimeError("boom")
        mock_resolve.return_value = self._session_with_members()
        session = self._session_with_members()
        reply = asyncio.run(run_agent("@Agent help", session))
        self.assertEqual(reply, orchestrator.FALLBACK_REPLY)

    @patch("server.main.send_message", new_callable=AsyncMock)
    @patch("server.main.run_agent", new_callable=AsyncMock)
    @patch("server.main.extract_and_merge", new_callable=AsyncMock)
    def test_webhook_sends_reply_when_agent_mentioned(
        self,
        mock_extract: AsyncMock,
        mock_run_agent: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        session = self._session_with_members()
        mock_extract.return_value = session
        mock_run_agent.return_value = "Here you go"

        payload = MessagePayload(
            group_id="group-1",
            sender="Johi",
            text="Need help @Agent",
            timestamp="2024-01-01T00:00:00Z",
        )

        asyncio.run(webhook(payload))

        mock_run_agent.assert_awaited_once()
        mock_send.assert_awaited_once_with("group-1", "Here you go")

    @patch("server.main.send_message", new_callable=AsyncMock)
    @patch("server.main.run_agent", new_callable=AsyncMock)
    @patch("server.main.extract_and_merge", new_callable=AsyncMock)
    def test_webhook_no_send_without_trigger(
        self,
        mock_extract: AsyncMock,
        mock_run_agent: AsyncMock,
        mock_send: AsyncMock,
    ) -> None:
        session = self._session_with_members()
        mock_extract.return_value = session

        payload = MessagePayload(
            group_id="group-1",
            sender="Johi",
            text="No trigger here",
            timestamp="2024-01-01T00:00:00Z",
        )

        asyncio.run(webhook(payload))

        mock_run_agent.assert_not_called()
        mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
