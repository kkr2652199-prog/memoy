from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float,
)
from sqlalchemy.orm import relationship
from app.db.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    source = Column(String(500), default="출처 미상 (사용자 직접 제공)")
    source_url = Column(String(2000), nullable=True, default=None, index=True)
    original_date = Column(String(50), nullable=True)
    ingested_date = Column(DateTime, default=_utcnow)

    category_large = Column(String(100), nullable=False)
    category_medium = Column(String(100), nullable=False)
    category_small = Column(String(100), nullable=True)

    summary = Column(Text, nullable=True)  # AI 요약
    content = Column(Text, nullable=True)  # 추출된 원문 전문(비요약)
    translated_content = Column(Text, nullable=True)  # 원문 한국어 번역 캐시(content 원본은 유지)
    wiki_body = Column(Text, nullable=True)  # 위키 .md 전문(검색·컨텍스트용, 파일과 동기화)
    raw_file_path = Column(String(1000), nullable=True)  # Raw_Materials/ 기준 상대 경로
    wiki_file_path = Column(String(1000), nullable=True)

    importance = Column(Integer, default=3)
    is_personal = Column(Boolean, default=False)
    tags = Column(JSON, default=list)
    status = Column(String(20), default="active")
    material_type = Column(String(20), default="information")

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    view_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, nullable=True)
    decay_score = Column(Float, default=1.0)
    memory_stage = Column(String(20), default="working")

    refs_from = relationship(
        "CrossReference",
        foreign_keys="CrossReference.material_id_from",
        back_populates="material_from",
        cascade="all, delete-orphan",
    )
    refs_to = relationship(
        "CrossReference",
        foreign_keys="CrossReference.material_id_to",
        back_populates="material_to",
        cascade="all, delete-orphan",
    )
    project_links = relationship(
        "ProjectMaterial", back_populates="material", cascade="all, delete-orphan"
    )


class CrossReference(Base):
    __tablename__ = "cross_references"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id_from = Column(Integer, ForeignKey("materials.id"), nullable=False)
    material_id_to = Column(Integer, ForeignKey("materials.id"), nullable=False)
    relation_type = Column(String(50), default="관련")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    material_from = relationship(
        "Material", foreign_keys=[material_id_from], back_populates="refs_from"
    )
    material_to = relationship(
        "Material", foreign_keys=[material_id_to], back_populates="refs_to"
    )


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="진행중")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    materials = relationship(
        "ProjectMaterial", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMaterial(Base):
    __tablename__ = "project_materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    note = Column(Text, nullable=True)
    added_at = Column(DateTime, default=_utcnow)

    project = relationship("Project", back_populates="materials")
    material = relationship("Material", back_populates="project_links")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), default="gpt")
    role = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    referenced_materials = Column(JSON, default=list)
    created_at = Column(DateTime, default=_utcnow)
    session_id = Column(String(64), nullable=True)
    quality_score = Column(Float, nullable=True)
    is_crystallized = Column(Boolean, default=False)
    crystallized_material_id = Column(Integer, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    related_material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)


class MaterialVersion(Base):
    __tablename__ = "material_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    title = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    changed_fields = Column(JSON, default=list)
    change_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(300), unique=True, nullable=False)
    type = Column(String(50), default="기타")
    wiki_path = Column(String(1000), nullable=True)
    mention_count = Column(Integer, default=1)
    first_seen = Column(DateTime, default=_utcnow)
    last_updated = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    grade = Column(String(1), default="B")  # "A" 또는 "B"
    confidence_score = Column(Float, default=0.5)
    source_count = Column(Integer, default=0)
    has_contradiction = Column(Boolean, default=False)
    last_verified = Column(DateTime, nullable=True)

    material_links = relationship(
        "MaterialEntity", back_populates="entity", cascade="all, delete-orphan"
    )


class Concept(Base):
    __tablename__ = "concepts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(300), unique=True, nullable=False)
    wiki_path = Column(String(1000), nullable=True)
    mention_count = Column(Integer, default=1)
    first_seen = Column(DateTime, default=_utcnow)
    last_updated = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    grade = Column(String(1), default="B")  # "A" 또는 "B"
    confidence_score = Column(Float, default=0.5)
    source_count = Column(Integer, default=0)
    has_contradiction = Column(Boolean, default=False)
    last_verified = Column(DateTime, nullable=True)

    material_links = relationship(
        "MaterialConcept", back_populates="concept", cascade="all, delete-orphan"
    )


class MaterialEntity(Base):
    __tablename__ = "material_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)

    material = relationship("Material")
    entity = relationship("Entity", back_populates="material_links")


class MaterialConcept(Base):
    __tablename__ = "material_concepts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    concept_id = Column(Integer, ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False)

    material = relationship("Material")
    concept = relationship("Concept", back_populates="material_links")


class Contradiction(Base):
    __tablename__ = "contradictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id_new = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    material_id_existing = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default="unresolved")
    detected_at = Column(DateTime, default=_utcnow)
    resolved_at = Column(DateTime, nullable=True)
    contradiction_type = Column(String(20), default="contradiction")
    # "contradiction" (진짜 모순), "supersession" (대체/업데이트)

    material_new = relationship("Material", foreign_keys=[material_id_new])
    material_existing = relationship("Material", foreign_keys=[material_id_existing])


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(200), unique=True, nullable=False)
    value = Column(Text, nullable=True)


class WeeklySnapshot(Base):
    __tablename__ = "weekly_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(DateTime, default=_utcnow)
    snapshot_type = Column(String(50), nullable=False)
    category_key = Column(String(200), nullable=False)
    count = Column(Integer, default=0)
    detail = Column(Text, nullable=True)
