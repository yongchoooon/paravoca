from __future__ import annotations

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
