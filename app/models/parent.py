"""
Parent model for parent authentication and management.
"""

from sqlalchemy import Column, Integer, String, Date
from .base import Base


class Parent(Base):
    """Parent model for parent authentication and management."""
    
    __tablename__ = "parents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uniqueid = Column(String(100), nullable=False)
    fatherName = Column(String(100), nullable=True)   # nullable: guardians may not have a father
    motherName = Column(String(100), nullable=True)   # nullable: father-role may not fill this
    fatherPhone = Column(String(100), nullable=True)  # nullable: mother/guardian role may not fill this
    motherPhone = Column(String(100), nullable=True)
    fatherJob = Column(String(100), nullable=True)
    motherJob = Column(String(100), nullable=True)
    pProvince = Column(String(100), nullable=True)
    pDistrict = Column(String(100), nullable=True)
    pCommune = Column(String(100), nullable=True)
    pVillage = Column(String(100), nullable=True)
    pEmail = Column(String(100), nullable=True)
    pTelegramId = Column(String(50), nullable=True)
    gName = Column(String(255), nullable=True)
    gPhone = Column(String(50), nullable=True)
    gIsThe = Column(String(100), nullable=True)
    gHome = Column(String(100), nullable=True)
    gStreet = Column(String(100), nullable=True)
    gGroup = Column(String(100), nullable=True)
    gProvince = Column(String(100), nullable=True)
    gDistrict = Column(String(100), nullable=True)
    gCommune = Column(String(100), nullable=True)
    gVillage = Column(String(100), nullable=True)
    myChilds = Column(String(255), nullable=True)
    created_at = Column(Date, nullable=False)
    updated_at = Column(Date, nullable=False)
    status = Column(Integer, nullable=False, default=1)
    username = Column(String(25), unique=True, index=True, nullable=True)
    password = Column(String(255), nullable=True)
    # Bumping this invalidates every token already issued to this parent, which
    # is the only way to end a session remotely. Employees have had it for a
    # while; parents did not, so a parent signed in on a stale or wrong session
    # could not be logged out at all.
    token_version = Column(Integer, nullable=True, default=1, server_default="1")

    def __repr__(self):
        return f"<Parent(id={self.id}, username='{self.username}', fatherName='{self.fatherName}', motherName='{self.motherName}')>"
