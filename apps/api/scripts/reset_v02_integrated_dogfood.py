"""Safely remove only the synthetic v0.2 dogfood fixture."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import models


MARKER = "[DOGFOOD]"


def _session() -> Session:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise SystemExit("DATABASE_URL is required; no rows were changed")
    return sessionmaker(bind=create_engine(value, pool_pre_ping=True), autoflush=False, expire_on_commit=False)()


def reset() -> int:
    session = _session()
    try:
        jobs = session.scalars(select(models.TargetJob).where(models.TargetJob.raw_text.like(f"{MARKER}%"))).all()
        profiles = {job.profile for job in jobs}
        for profile in profiles:
            if any(not (job.raw_text or "").startswith(MARKER) for job in profile.target_jobs):
                raise SystemExit("refusing to delete a profile that also owns non-dogfood target jobs")
            if any(not (item.evidence_text or "").startswith(MARKER) for item in profile.experiences):
                raise SystemExit("refusing to delete a profile with non-dogfood experiences")
        for profile in profiles:
            session.delete(profile)
        session.commit()
        print(f"DOGFOOD_RESET profiles={len(profiles)} jobs={len(jobs)}")
        return len(profiles)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    reset()
