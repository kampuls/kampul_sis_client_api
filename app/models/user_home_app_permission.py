from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


class UserHomeAppPermission(Base):
    """
    Per-user home feature access override.
    This does not replace existing roles/permissions; it adds a separate layer.
    """

    __tablename__ = "user_home_app_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "feature_id", name="uq_user_home_feature"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    feature_id = Column(String(100), nullable=False, index=True)
    is_allowed = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
