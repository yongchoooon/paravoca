from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db import models

settings = get_settings()

if settings.sqlite_path is not None:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_workflow_runs_revision_columns()
    migrate_tourism_item_geo_columns()
    with SessionLocal() as db:
        seed_default_workflow(db)


def check_db() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def migrate_workflow_runs_revision_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(workflow_runs)")).mappings().all()
        existing_columns = {row["name"] for row in rows}
        if "parent_run_id" not in existing_columns:
            connection.execute(text("ALTER TABLE workflow_runs ADD COLUMN parent_run_id VARCHAR(120)"))
        if "revision_number" not in existing_columns:
            connection.execute(
                text("ALTER TABLE workflow_runs ADD COLUMN revision_number INTEGER NOT NULL DEFAULT 0")
            )
        if "revision_mode" not in existing_columns:
            connection.execute(text("ALTER TABLE workflow_runs ADD COLUMN revision_mode VARCHAR(40)"))


def migrate_tourism_item_geo_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    columns = {
        "legacy_area_code": "VARCHAR(40)",
        "legacy_sigungu_code": "VARCHAR(40)",
        "ldong_regn_cd": "VARCHAR(40)",
        "ldong_signgu_cd": "VARCHAR(40)",
        "lcls_systm_1": "VARCHAR(40)",
        "lcls_systm_2": "VARCHAR(40)",
        "lcls_systm_3": "VARCHAR(40)",
    }
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(tourism_items)")).mappings().all()
        existing_columns = {row["name"] for row in rows}
        for name, column_type in columns.items():
            if name not in existing_columns:
                connection.execute(text(f"ALTER TABLE tourism_items ADD COLUMN {name} {column_type}"))


def seed_default_workflow(db: Session) -> None:
    template = db.get(models.WorkflowTemplate, "default_product_planning")
    if template:
        return

    template = models.WorkflowTemplate(
        id="default_product_planning",
        name="Default Product Planning",
        description="TourAPI 기반 상품 기획 기본 workflow",
        is_default=True,
        nodes=[
            {"id": "user_input", "type": "user_input", "position": {"x": 0, "y": 120}, "config": {}},
            {"id": "planner", "type": "planner_agent", "position": {"x": 260, "y": 120}, "config": {}},
            {"id": "geo_resolver", "type": "geo_resolver_agent", "position": {"x": 520, "y": 120}, "config": {}},
            {"id": "data_agent", "type": "data_agent", "position": {"x": 780, "y": 120}, "config": {"provider": "tourapi"}},
            {"id": "human_approval", "type": "human_approval", "position": {"x": 1040, "y": 120}, "config": {"required": True}},
        ],
        edges=[
            {"id": "edge_user_planner", "source": "user_input", "target": "planner"},
            {"id": "edge_planner_geo", "source": "planner", "target": "geo_resolver"},
            {"id": "edge_geo_data", "source": "geo_resolver", "target": "data_agent"},
            {"id": "edge_data_approval", "source": "data_agent", "target": "human_approval"},
        ],
    )
    db.add(template)
    db.commit()
