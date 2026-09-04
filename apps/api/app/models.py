from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    education: Mapped[list[Education]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    skills: Mapped[list[ProfileSkill]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    experiences: Mapped[list[Experience]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    certifications: Mapped[list[Certification]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class ProfileChild:
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="USER_ENTERED")


class Education(ProfileChild, Base):
    __tablename__ = "education"

    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dates: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile: Mapped[UserProfile] = relationship(back_populates="education")


class ProfileSkill(ProfileChild, Base):
    __tablename__ = "profile_skills"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    proficiency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    profile: Mapped[UserProfile] = relationship(back_populates="skills")


class Experience(ProfileChild, Base):
    __tablename__ = "experiences"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dates: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile: Mapped[UserProfile] = relationship(back_populates="experiences")


class Certification(ProfileChild, Base):
    __tablename__ = "certifications"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile: Mapped[UserProfile] = relationship(back_populates="certifications")
