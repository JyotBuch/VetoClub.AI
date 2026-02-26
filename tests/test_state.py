"""Unit tests for Layer 2 state and preference logic."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest

from server.state import preferences
from server.state import session as session_store
from server.state.models import GroupSession


class StateLayerTests(unittest.TestCase):
    """Acceptance criteria coverage for the in-memory state layer."""

    def setUp(self) -> None:
        session_store._sessions.clear()  # type: ignore[attr-defined]

    def test_get_or_create_returns_same_instance(self) -> None:
        first = session_store.get_or_create("group-1")
        second = session_store.get_or_create("group-1")

        self.assertIs(first, second)

    def test_upsert_member_creates_and_merges(self) -> None:
        session = session_store.get_or_create("group-merge")

        preferences.upsert_member(
            session,
            "Alex",
            {
                "dietary": ["vegetarian"],
                "confirmed": False,
                "cuisine_likes": ["thai"],
            },
        )

        preferences.upsert_member(
            session,
            "Alex",
            {
                "cuisine_dislikes": ["indian"],
            },
        )

        member = session.members["Alex"]
        self.assertEqual(member.dietary, ["vegetarian"])
        self.assertEqual(member.cuisine_likes, ["thai"])
        self.assertEqual(member.cuisine_dislikes, ["indian"])

    def test_all_confirmed_false_when_no_members(self) -> None:
        session = session_store.get_or_create("group-empty")

        self.assertFalse(preferences.all_confirmed(session))

    def test_merge_dietary_returns_deduplicated_union(self) -> None:
        session = session_store.get_or_create("group-dietary")
        preferences.upsert_member(session, "Priya", {"dietary": ["vegetarian"]})
        preferences.upsert_member(
            session,
            "Zain",
            {"dietary": ["halal", "vegetarian"]},
        )

        merged = preferences.merge_dietary(session)

        self.assertEqual(set(merged), {"vegetarian", "halal"})
        self.assertEqual(len(merged), 2)

    def test_message_history_capped_at_twenty(self) -> None:
        session = GroupSession(group_id="group-history")

        for i in range(21):
            session.append_message(
                {"idx": i, "timestamp": datetime.now(timezone.utc).isoformat()}
            )

        self.assertEqual(len(session.message_history), 20)
        stored_indices = [entry["idx"] for entry in session.message_history]
        self.assertEqual(stored_indices[0], 1)
        self.assertEqual(stored_indices[-1], 20)


if __name__ == "__main__":
    unittest.main()
