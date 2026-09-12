"""Regression tests for chat group membership scoping.

``message_group_members.user_id`` points into ``users``, ``parents`` or
``students`` depending on ``user_type``. Matching on the ID alone let parent #57
read (and post into) every group employee #57 belonged to.
"""

import unittest
from datetime import date

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.messages import _membership_of, _require_membership
from app.auth.dependencies import (
    PARENT_MEMBER_TYPES,
    STAFF_MEMBER_TYPES,
    STUDENT_MEMBER_TYPES,
    Principal,
)
from app.models import MessageGroup, MessageGroupMember
from app.models.base import Base


class ChatMembershipIsolationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[MessageGroup.__table__, MessageGroupMember.__table__],
        )
        self.db = sessionmaker(bind=self.engine)()

        self.db.add(
            MessageGroup(id=10, name="Staff room", type="custom", created_by=1)
        )
        # Only the EMPLOYEE with id 57 is a member of this group.
        self.db.add(
            MessageGroupMember(
                group_id=10, user_id=57, user_type="teacher", role="admin"
            )
        )

        self.db.add(
            MessageGroup(id=20, name="Grade 1 parents", type="class", created_by=1)
        )
        # Only the PARENT with id 57 is a member of this one.
        self.db.add(
            MessageGroupMember(
                group_id=20, user_id=57, user_type="parent", role="member"
            )
        )
        self.db.commit()

        self.staff_57 = Principal(57, "teacher", STAFF_MEMBER_TYPES)
        self.parent_57 = Principal(57, "parent", PARENT_MEMBER_TYPES)
        self.student_57 = Principal(57, "student", STUDENT_MEMBER_TYPES)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_parent_is_not_a_member_of_the_staff_group(self):
        self.assertIsNone(_membership_of(self.db, 10, self.parent_57))
        with self.assertRaises(HTTPException) as raised:
            _require_membership(self.db, 10, self.parent_57)
        self.assertEqual(raised.exception.status_code, 403)

    def test_staff_is_not_a_member_of_the_parent_group(self):
        self.assertIsNone(_membership_of(self.db, 20, self.staff_57))

    def test_student_sharing_the_id_is_not_a_member_of_either(self):
        self.assertIsNone(_membership_of(self.db, 10, self.student_57))
        self.assertIsNone(_membership_of(self.db, 20, self.student_57))

    def test_each_principal_still_sees_its_own_group(self):
        self.assertIsNotNone(_membership_of(self.db, 10, self.staff_57))
        self.assertIsNotNone(_membership_of(self.db, 20, self.parent_57))

    def test_employee_membership_row_also_matches_the_teacher_alias(self):
        """Staff rows are stored as 'teacher' or 'employee'; both must resolve."""
        self.db.add(
            MessageGroup(id=30, name="Ops", type="custom", created_by=1)
        )
        self.db.add(
            MessageGroupMember(
                group_id=30, user_id=57, user_type="employee", role="member"
            )
        )
        self.db.commit()
        self.assertIsNotNone(_membership_of(self.db, 30, self.staff_57))
        self.assertIsNone(_membership_of(self.db, 30, self.parent_57))


if __name__ == "__main__":
    unittest.main()


class ReactionOwnershipTests(unittest.TestCase):
    """A reaction belongs to (user_id, user_type), never user_id alone."""

    def setUp(self):
        from app.models.message import GroupMessage, MessageReaction

        self.MessageReaction = MessageReaction
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                MessageGroup.__table__,
                GroupMessage.__table__,
                MessageReaction.__table__,
            ],
        )
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(MessageGroup(id=1, name="G", type="custom", created_by=1))
        self.db.add(GroupMessage(id=1, group_id=1, sender_id=1, content="hi"))
        # The EMPLOYEE with id 57 reacted.
        self.db.add(
            MessageReaction(
                id=1, message_id=1, user_id=57, user_type="teacher", reaction="👍"
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _owner_match(self, reaction, principal):
        return (
            reaction.user_id == principal.id
            and reaction.user_type in principal.member_types
        )

    def test_parent_does_not_own_the_employees_reaction(self):
        reaction = self.db.get(self.MessageReaction, 1)
        self.assertFalse(
            self._owner_match(reaction, Principal(57, "parent", PARENT_MEMBER_TYPES))
        )

    def test_the_employee_still_owns_it(self):
        reaction = self.db.get(self.MessageReaction, 1)
        self.assertTrue(
            self._owner_match(reaction, Principal(57, "teacher", STAFF_MEMBER_TYPES))
        )

    def test_model_carries_a_user_type_column(self):
        self.assertIn("user_type", self.MessageReaction.__table__.columns)
