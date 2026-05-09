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
    nodes = [
        {"id": "user_input", "type": "user_input", "position": {"x": 0, "y": 120}, "config": {}},
        {"id": "planner", "type": "planner_agent", "position": {"x": 220, "y": 120}, "config": {}},
        {"id": "geo_resolver", "type": "geo_resolver_agent", "position": {"x": 440, "y": 120}, "config": {}},
        {
            "id": "baseline_data",
            "type": "baseline_data_agent",
            "position": {"x": 660, "y": 120},
            "config": {"provider": "tourapi"},
        },
        {
            "id": "data_gap_profiler",
            "type": "data_gap_profiler_agent",
            "position": {"x": 880, "y": 120},
            "config": {},
        },
        {
            "id": "api_capability_router",
            "type": "api_capability_router_agent",
            "position": {"x": 1100, "y": 120},
            "config": {"max_call_budget": "settings.enrichment_max_call_budget"},
        },
        {
            "id": "tourapi_detail_planner",
            "type": "tourapi_detail_planner_agent",
            "position": {"x": 1320, "y": -40},
            "config": {},
        },
        {
            "id": "visual_data_planner",
            "type": "visual_data_planner_agent",
            "position": {"x": 1320, "y": 80},
            "config": {},
        },
        {
            "id": "route_signal_planner",
            "type": "route_signal_planner_agent",
            "position": {"x": 1320, "y": 200},
            "config": {},
        },
        {
            "id": "theme_data_planner",
            "type": "theme_data_planner_agent",
            "position": {"x": 1320, "y": 320},
            "config": {},
        },
        {
            "id": "data_enrichment",
            "type": "enrichment_executor",
            "position": {"x": 1540, "y": 120},
            "config": {},
        },
        {
            "id": "evidence_fusion",
            "type": "evidence_fusion_agent",
            "position": {"x": 1760, "y": 120},
            "config": {},
        },
        {"id": "research", "type": "research_agent", "position": {"x": 1980, "y": 120}, "config": {}},
        {"id": "product", "type": "product_agent", "position": {"x": 2200, "y": 120}, "config": {}},
        {"id": "marketing", "type": "marketing_agent", "position": {"x": 2420, "y": 120}, "config": {}},
        {"id": "qa", "type": "qa_agent", "position": {"x": 2640, "y": 120}, "config": {}},
        {
            "id": "human_approval",
            "type": "human_approval",
            "position": {"x": 2860, "y": 120},
            "config": {"required": True},
        },
    ]
    edges = [
        {"id": "edge_user_planner", "source": "user_input", "target": "planner"},
        {"id": "edge_planner_geo", "source": "planner", "target": "geo_resolver"},
        {"id": "edge_geo_baseline", "source": "geo_resolver", "target": "baseline_data"},
        {"id": "edge_baseline_gap", "source": "baseline_data", "target": "data_gap_profiler"},
        {"id": "edge_gap_router", "source": "data_gap_profiler", "target": "api_capability_router"},
        {"id": "edge_router_detail_planner", "source": "api_capability_router", "target": "tourapi_detail_planner"},
        {"id": "edge_router_visual_planner", "source": "api_capability_router", "target": "visual_data_planner"},
        {"id": "edge_router_route_planner", "source": "api_capability_router", "target": "route_signal_planner"},
        {"id": "edge_router_theme_planner", "source": "api_capability_router", "target": "theme_data_planner"},
        {"id": "edge_detail_planner_enrichment", "source": "tourapi_detail_planner", "target": "data_enrichment"},
        {"id": "edge_visual_planner_enrichment", "source": "visual_data_planner", "target": "data_enrichment"},
        {"id": "edge_route_planner_enrichment", "source": "route_signal_planner", "target": "data_enrichment"},
        {"id": "edge_theme_planner_enrichment", "source": "theme_data_planner", "target": "data_enrichment"},
        {"id": "edge_enrichment_fusion", "source": "data_enrichment", "target": "evidence_fusion"},
        {"id": "edge_fusion_research", "source": "evidence_fusion", "target": "research"},
        {"id": "edge_research_product", "source": "research", "target": "product"},
        {"id": "edge_product_marketing", "source": "product", "target": "marketing"},
        {"id": "edge_marketing_qa", "source": "marketing", "target": "qa"},
        {"id": "edge_qa_approval", "source": "qa", "target": "human_approval"},
    ]
    template = db.get(models.WorkflowTemplate, "default_product_planning")
    if template:
        template.description = "TourAPI 기반 상품 기획과 선택적 data enrichment workflow"
        template.nodes = nodes
        template.edges = edges
        template.updated_at = models.utcnow()
        db.commit()
        return

    template = models.WorkflowTemplate(
        id="default_product_planning",
        name="Default Product Planning",
        description="TourAPI 기반 상품 기획과 선택적 data enrichment workflow",
        is_default=True,
        nodes=nodes,
        edges=edges,
    )
    db.add(template)
    db.commit()
