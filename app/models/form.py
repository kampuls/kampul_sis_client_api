from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from .base import Base

class TargetRole(str, enum.Enum):
    ALL = "all"
    PARENTS = "parents"
    STUDENTS = "students"
    TEACHERS = "teachers"

class FieldType(str, enum.Enum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    NUMBER = "number"
    DROPDOWN = "dropdown"
    CHECKBOXES = "checkboxes"
    RADIO = "radio"
    DATE = "date"
    TIME = "time"
    CHILD_SELECTOR = "child_selector"
    IMAGE = "image"
    FILE = "file"

class Form(Base):
    __tablename__ = "forms"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    target_role = Column(Enum(TargetRole, values_callable=lambda obj: [e.value for e in obj]), default=TargetRole.ALL, nullable=False)
    allow_multiple_submissions = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    image_url = Column(String(500), nullable=True)  # Optional form cover/header image
    start_date = Column(DateTime(timezone=True), nullable=True) # Optional form starting date
    end_date = Column(DateTime(timezone=True), nullable=True) # Optional form ending/expire date
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    fields = relationship("FormField", back_populates="form", cascade="all, delete-orphan", order_by="FormField.order")
    submissions = relationship("FormSubmission", back_populates="form", cascade="all, delete-orphan")

class FormField(Base):
    __tablename__ = "form_fields"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    form_id = Column(Integer, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False)
    field_type = Column(Enum(FieldType, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    label = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)   # Optional illustrative image for this question
    display_only = Column(Boolean, default=False, nullable=False)  # Show as info block, no answer needed
    is_required = Column(Boolean, default=False, nullable=False)
    order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    form = relationship("Form", back_populates="fields")
    options = relationship("FormFieldOption", back_populates="field", cascade="all, delete-orphan", order_by="FormFieldOption.order")

class FormFieldOption(Base):
    __tablename__ = "form_field_options"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    field_id = Column(Integer, ForeignKey("form_fields.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(255), nullable=False)
    value = Column(String(255), nullable=False)
    order = Column(Integer, default=0, nullable=False)

    # Relationships
    field = relationship("FormField", back_populates="options")

class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    form_id = Column(Integer, ForeignKey("forms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, nullable=False) # ID of parent/student/teacher
    user_type = Column(Enum(TargetRole, values_callable=lambda obj: [e.value for e in obj]), nullable=False) # What type of user submitted this
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    form = relationship("Form", back_populates="submissions")
    values = relationship("FormSubmissionValue", back_populates="submission", cascade="all, delete-orphan")

class FormSubmissionValue(Base):
    __tablename__ = "form_submission_values"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(Integer, ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=False)
    field_id = Column(Integer, ForeignKey("form_fields.id", ondelete="CASCADE"), nullable=False)
    value = Column(Text, nullable=True) # Text value, or selected option value, or uploaded file URL, or child ID

    # Relationships
    submission = relationship("FormSubmission", back_populates="values")
