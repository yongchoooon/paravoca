from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KtoOperationCapability(BaseModel):
    tool_name: str
    operation: str
    purpose: str
    implemented: bool
    workflow_enabled: bool
    required_for_phase: str


class KtoSourceCapability(BaseModel):
    source_family: str
    display_name: str
    category: str
    enabled: bool
    requires_service_key: bool
    required_env_vars: list[str] = Field(default_factory=list)
    configured_env_vars: list[str] = Field(default_factory=list)
    missing_env_vars: list[str] = Field(default_factory=list)
    source_setting_env: str | None = None
    source_setting_enabled: bool
    supported_gaps: list[str] = Field(default_factory=list)
    default_ttl_hours: int
    risk_level: str
    operations: list[KtoOperationCapability] = Field(default_factory=list)
    disabled_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DataSourceCapabilitiesResponse(BaseModel):
    sources: list[KtoSourceCapability]
    enabled_count: int
    implemented_operation_count: int
    workflow_operation_count: int


class DataSourceInventoryStats(BaseModel):
    tourism_items: int = 0
    source_documents: int = 0
    indexed_documents: int = 0
    visual_assets: int = 0
    route_assets: int = 0
    signal_records: int = 0
    enrichment_calls: int = 0
    successful_enrichment_calls: int = 0
    failed_enrichment_calls: int = 0
    latest_activity_at: datetime | None = None


class DataSourcePurposeProfile(BaseModel):
    key: str
    label: str


class DataSourceOverviewItem(KtoSourceCapability):
    purpose: str
    input_fields: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)
    example_use: str
    origin_description: str
    purpose_tags: list[str] = Field(default_factory=list)
    stored_count: int
    evidence_count: int
    readiness_status: str
    status_label: str
    status_detail: str
    implemented_operation_count: int
    workflow_operation_count: int
    inventory: DataSourceInventoryStats


class DataSourceCatalogStatus(BaseModel):
    key: str
    label: str
    record_count: int
    status: str
    status_label: str
    last_synced_at: datetime | None = None


class DataSourceDocumentStatus(BaseModel):
    total: int
    indexed: int
    pending: int
    failed: int
    status: str
    status_label: str
    latest_updated_at: datetime | None = None


class DataSourceTourismInventory(BaseModel):
    total_items: int
    items_with_image: int
    content_type_counts: dict[str, int] = Field(default_factory=dict)
    latest_synced_at: datetime | None = None


class DataSourceDocumentPreview(BaseModel):
    id: str
    title: str
    source: str
    source_family: str
    source_role: str = "unknown"
    source_label: str
    source_item_id: str
    source_item_title: str | None = None
    content_excerpt: str
    content: str
    embedding_status: str
    status_label: str
    content_type: str | None = None
    address: str | None = None
    origin_summary: str
    usage_summary: str
    lifecycle_summary: str | None = None
    updated_at: datetime | None = None


class DataSourceDocumentBrowserResponse(BaseModel):
    items: list[DataSourceDocumentPreview]
    total: int
    limit: int


class DataSourceTourismItemPreview(BaseModel):
    id: str
    title: str
    source: str
    source_family: str
    source_label: str
    content_id: str
    content_type: str
    content_type_label: str
    address: str | None = None
    ldong_label: str | None = None
    classification_label: str | None = None
    has_image: bool
    has_ai_evidence: bool
    origin_summary: str
    detail_summary: str
    last_synced_at: datetime | None = None


class DataSourceTourismItemBrowserResponse(BaseModel):
    items: list[DataSourceTourismItemPreview]
    total: int
    limit: int


class DataSourceRegionCatalogItem(BaseModel):
    id: str
    region_code: str
    region_name: str
    signgu_code: str | None = None
    signgu_name: str | None = None
    full_name: str
    tourism_item_count: int
    synced_at: datetime | None = None


class DataSourceClassificationCatalogItem(BaseModel):
    id: str
    code_path: list[str] = Field(default_factory=list)
    name_path: list[str] = Field(default_factory=list)
    content_type_id: str | None = None
    content_type_name: str | None = None
    full_name: str
    tourism_item_count: int
    synced_at: datetime | None = None


class DataSourceCatalogBrowserResponse(BaseModel):
    regions: list[DataSourceRegionCatalogItem]
    classifications: list[DataSourceClassificationCatalogItem]
    region_total: int
    classification_total: int
    limit: int
    region_offset: int = 0
    classification_offset: int = 0


class DataSourceOverviewSummary(BaseModel):
    total_sources: int
    ready_sources: int
    setup_required_sources: int
    disabled_sources: int
    implemented_operation_count: int
    workflow_operation_count: int
    tourism_item_count: int
    source_document_count: int
    indexed_document_count: int
    enrichment_run_count: int
    latest_activity_at: datetime | None = None


class DataSourceOverviewResponse(BaseModel):
    purpose: str
    purpose_detail: str
    summary: DataSourceOverviewSummary
    sources: list[DataSourceOverviewItem]
    catalogs: list[DataSourceCatalogStatus]
    documents: DataSourceDocumentStatus
    tourism_inventory: DataSourceTourismInventory
    purpose_profiles: list[DataSourcePurposeProfile] = Field(default_factory=list)
