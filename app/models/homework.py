"""Class-bound homework publishing models."""

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class LearningHomework(Base):
    __tablename__ = "learning_homework"

    id = Column(Integer, primary_key=True, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    class_schedule_id = Column(
        Integer,
        ForeignKey("learning_class_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    branch_id = Column(Integer, nullable=False)
    program_id = Column(Integer, nullable=False)
    grade_group_id = Column(Integer, nullable=False)
    grade_id = Column(Integer, nullable=True)
    grade_type_id = Column(Integer, nullable=True)
    shift_id = Column(Integer, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    homework_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    attachments = relationship(
        "LearningHomeworkAttachment",
        back_populates="homework",
        cascade="all, delete-orphan",
        order_by="LearningHomeworkAttachment.id",
    )


class LearningHomeworkAttachment(Base):
    __tablename__ = "learning_homework_attachments"

    id = Column(Integer, primary_key=True, index=True)
    homework_id = Column(
        Integer,
        ForeignKey("learning_homework.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_url = Column(String(1000), nullable=False)
    original_name = Column(String(255), nullable=False)
    content_type = Column(String(150), nullable=False)
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    homework = relationship("LearningHomework", back_populates="attachments")
