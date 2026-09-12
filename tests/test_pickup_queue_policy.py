import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from app.api.v1 import pickup, websocket
from app.core.auto_index import INDEX_MIGRATIONS


class PickupQueuePolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        pickup._stale_cleanup_last_by_academic.clear()

    async def test_parent_cannot_read_staff_queue(self):
        db = Mock()
        parent = SimpleNamespace(id=8, role="parent", is_parent=True)

        with self.assertRaises(HTTPException) as caught:
            await pickup.get_pickup_queue(16, None, db, parent)

        self.assertEqual(caught.exception.status_code, 403)
        db.execute.assert_not_called()

    async def test_parent_can_only_cancel_own_request(self):
        db = Mock()
        db.execute.return_value.fetchone.return_value = (
            41,
            99,
            7,
            16,
            "pending",
        )
        parent = SimpleNamespace(id=8, role="parent", is_parent=True)

        with self.assertRaises(HTTPException) as caught:
            await pickup.cancel_request(41, {"academic_id": 16}, db, parent)

        self.assertEqual(caught.exception.status_code, 403)
        db.rollback.assert_called_once()
        db.commit.assert_not_called()

    async def test_repeat_retry_returns_committed_counter_without_incrementing(self):
        db = Mock()
        db.execute.return_value.fetchone.return_value = (
            41,
            3,
            1,
            "processing",
            7,
            8,
            16,
        )
        staff = SimpleNamespace(id=2, role=2)

        with patch.object(pickup, "_broadcast_queue", new=AsyncMock()) as broadcast:
            result = await pickup.advance_repeat(
                41,
                {"academic_id": 16, "expected_current_repeat": 0},
                db,
                staff,
            )

        self.assertTrue(result["already_advanced"])
        self.assertEqual(result["current_repeat"], 1)
        db.rollback.assert_called_once()
        db.commit.assert_not_called()
        broadcast.assert_not_awaited()

    def test_pickup_hot_paths_have_composite_indexes(self):
        names = {
            migration["name"]
            for migration in INDEX_MIGRATIONS
            if migration["table"] == "pickup_requests"
        }
        self.assertTrue(
            {
                "idx_pickup_academic_status_requested",
                "idx_pickup_branch_queue",
                "idx_pickup_parent_student_latest",
                "idx_pickup_student_active",
            }.issubset(names)
        )

    def test_stale_cleanup_is_throttled_per_academic_year(self):
        db = Mock()
        now = datetime(2026, 8, 3, 8, 0)

        pickup._expire_stale_pickup_requests(db, 16, now)
        pickup._expire_stale_pickup_requests(
            db,
            16,
            now + timedelta(seconds=30),
        )

        db.execute.assert_called_once()
        db.commit.assert_called_once()

    def test_parent_cannot_join_pickup_admin_realtime_room(self):
        parent = SimpleNamespace(id=8, role="parent", is_parent=True)
        staff = SimpleNamespace(id=2, role=2)

        self.assertFalse(websocket._can_join_room(parent, "pickup_admin_16"))
        self.assertTrue(websocket._can_join_room(staff, "pickup_admin_16"))
        self.assertTrue(websocket._can_join_room(parent, "pickup_parents_16"))


if __name__ == "__main__":
    unittest.main()
