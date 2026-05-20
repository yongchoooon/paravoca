from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.core.config import Settings, get_settings
from app.db import models
from app.db.session import SessionLocal, get_db
from app.posters.openai_images import (
    PosterImageGenerationError,
    generate_poster_image,
)
from app.posters.presets import DEFAULT_INCLUDED_SECTIONS, POSTER_STYLE_PRESETS
from app.posters.prompt_log import safe_write_poster_prompt_log
from app.posters.prompt_builder import build_poster_prompt
from app.posters.usage_log import safe_write_poster_usage_log
from app.schemas.posters import (
    PosterAssetRead,
    PosterCreateRequest,
    PosterDeleteResult,
    PosterStudioOptions,
)


router = APIRouter(tags=["posters"])

BLOCKED_RESULT_STATUSES = {"failed", "insufficient_source_data", "cancelled", "unsupported"}
BLOCKED_RUN_STATUSES = {"failed", "cancelled", "cancelling"}
ACTIVE_POSTER_STATUSES = {"pending", "running"}
COUNTED_POSTER_STATUSES = {"pending", "running", "succeeded"}
MAX_POSTERS_PER_PRODUCT = 3


@router.get("/posters/options")
def get_poster_options(settings: Settings = Depends(get_settings)) -> dict:
    options = PosterStudioOptions(
        style_presets=[
            {
                "id": preset.id,
                "label": preset.label,
                "description": preset.description,
            }
            for preset in POSTER_STYLE_PRESETS.values()
        ],
        default_included_sections=DEFAULT_INCLUDED_SECTIONS,
        image_size=settings.poster_image_size,
        image_quality=settings.poster_image_quality,
        image_model=settings.poster_image_model,
        usd_krw_rate=float(settings.usd_krw_rate or 0),
        max_posters_per_product=MAX_POSTERS_PER_PRODUCT,
    )
    return ok(options.model_dump())


@router.get("/posters")
def list_posters(
    run_id: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    include_evaluation: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(models.PosterAsset).order_by(models.PosterAsset.created_at.desc())
    if run_id:
        query = query.filter(models.PosterAsset.run_id == run_id)
    if product_id:
        query = query.filter(models.PosterAsset.product_id == product_id)
    posters = query.limit(200).all()
    if not include_evaluation:
        posters = [poster for poster in posters if not _is_evaluation_run(poster.run)]
    return ok([_poster_read(poster) for poster in posters], count=len(posters))


@router.get("/posters/{poster_id}")
def get_poster(poster_id: str, db: Session = Depends(get_db)) -> dict:
    poster = db.get(models.PosterAsset, poster_id)
    if not poster:
        raise HTTPException(status_code=404, detail="Poster asset not found")
    return ok(_poster_read(poster))


@router.get("/workflow-runs/{run_id}/posters")
def list_run_posters(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = _get_run_or_404(db, run_id)
    posters = (
        db.query(models.PosterAsset)
        .filter(models.PosterAsset.run_id == run.id)
        .order_by(models.PosterAsset.created_at.desc())
        .all()
    )
    return ok([_poster_read(poster) for poster in posters], count=len(posters))


@router.post("/workflow-runs/{run_id}/products/{product_id}/posters")
def create_product_poster(
    run_id: str,
    product_id: str,
    payload: PosterCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    run = _get_run_or_404(db, run_id)
    result = _result_or_409(run)
    _ensure_generation_allowed(run, result)
    product = _find_product(result, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found in workflow run result")

    included_sections = payload.included_sections or DEFAULT_INCLUDED_SECTIONS
    _ensure_no_duplicate_running_poster(
        db,
        run_id=run.id,
        product_id=product_id,
        style_preset=payload.style_preset,
        included_sections=included_sections,
    )
    _ensure_product_poster_limit(db, run_id=run.id, product_id=product_id)

    marketing = _find_marketing(result, product_id)
    prompt_result = build_poster_prompt(
        run_input=run.input if isinstance(run.input, dict) else {},
        result=result,
        product=product,
        marketing=marketing,
        included_sections=included_sections,
        style_preset=payload.style_preset,
        input_images=list(payload.input_images or []),
    )

    poster = models.PosterAsset(
        run_id=run.id,
        product_id=product_id,
        product_title=str(product.get("title") or product_id),
        style_preset=payload.style_preset,
        included_sections=included_sections,
        input_images=list(payload.input_images or []),
        prompt=prompt_result.prompt,
        prompt_language="en",
        image_model=settings.poster_image_model,
        image_size=settings.poster_image_size,
        image_quality=settings.poster_image_quality,
        provider="openai",
        provider_response_summary={"prompt_source": prompt_result.source_summary},
        status="running",
    )
    db.add(poster)
    db.commit()
    db.refresh(poster)
    _log_poster_prompt(poster, settings)
    background_tasks.add_task(_generate_poster_background, poster.id)
    return ok(_poster_read(poster))


@router.delete("/posters/{poster_id}")
def delete_poster(poster_id: str, db: Session = Depends(get_db)) -> dict:
    poster = db.get(models.PosterAsset, poster_id)
    if not poster:
        raise HTTPException(status_code=404, detail="Poster asset not found")
    if poster.status in ACTIVE_POSTER_STATUSES:
        raise HTTPException(status_code=409, detail="Running poster generation cannot be deleted")
    deleted_image_path = poster.image_path
    if deleted_image_path:
        _delete_file_if_exists(Path(deleted_image_path))
    db.delete(poster)
    db.commit()
    return ok(
        PosterDeleteResult(
            deleted_poster_id=poster_id,
            deleted_image_path=deleted_image_path,
        ).model_dump()
    )


@router.get("/posters/{poster_id}/download")
def download_poster(poster_id: str, db: Session = Depends(get_db)) -> FileResponse:
    poster = db.get(models.PosterAsset, poster_id)
    if not poster:
        raise HTTPException(status_code=404, detail="Poster asset not found")
    if poster.status != "succeeded" or not poster.image_path:
        raise HTTPException(status_code=409, detail="Poster image is not available for download")
    path = Path(poster.image_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Poster image file not found")
    filename = _download_filename(poster)
    return FileResponse(path, media_type="image/png", filename=filename)


def _get_run_or_404(db: Session, run_id: str) -> models.WorkflowRun:
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return run


def _result_or_409(run: models.WorkflowRun) -> dict[str, Any]:
    if not isinstance(run.final_output, dict):
        raise HTTPException(
            status_code=409,
            detail="Workflow run does not have a generated product result yet",
        )
    return run.final_output


def _ensure_generation_allowed(run: models.WorkflowRun, result: dict[str, Any]) -> None:
    if run.status in BLOCKED_RUN_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Poster generation is not available for run status: {run.status}",
        )
    result_status = str(result.get("status") or "").lower()
    if result_status in BLOCKED_RESULT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Poster generation is not available for result status: {result_status}",
        )
    if not _products(result):
        raise HTTPException(status_code=409, detail="Workflow run has no products to posterize")


def _products(result: dict[str, Any]) -> list[dict[str, Any]]:
    products = result.get("products")
    if not isinstance(products, list):
        return []
    return [product for product in products if isinstance(product, dict)]


def _find_product(result: dict[str, Any], product_id: str) -> dict[str, Any] | None:
    for product in _products(result):
        if str(product.get("id")) == product_id:
            return product
    return None


def _find_marketing(result: dict[str, Any], product_id: str) -> dict[str, Any] | None:
    marketing_assets = result.get("marketing_assets")
    if not isinstance(marketing_assets, list):
        return None
    for asset in marketing_assets:
        if isinstance(asset, dict) and str(asset.get("product_id")) == product_id:
            return asset
    return None


def _ensure_no_duplicate_running_poster(
    db: Session,
    *,
    run_id: str,
    product_id: str,
    style_preset: str,
    included_sections: list[str],
) -> None:
    posters = (
        db.query(models.PosterAsset)
        .filter(
            models.PosterAsset.run_id == run_id,
            models.PosterAsset.product_id == product_id,
            models.PosterAsset.style_preset == style_preset,
            models.PosterAsset.status.in_(ACTIVE_POSTER_STATUSES),
        )
        .all()
    )
    target_sections = list(included_sections)
    for poster in posters:
        if list(poster.included_sections or []) == target_sections:
            raise HTTPException(
                status_code=409,
                detail="Poster generation is already running for this product and option set",
            )


def _ensure_product_poster_limit(db: Session, *, run_id: str, product_id: str) -> None:
    count = (
        db.query(models.PosterAsset)
        .filter(
            models.PosterAsset.run_id == run_id,
            models.PosterAsset.product_id == product_id,
            models.PosterAsset.status.in_(COUNTED_POSTER_STATUSES),
        )
        .count()
    )
    if count >= MAX_POSTERS_PER_PRODUCT:
        raise HTTPException(
            status_code=409,
            detail=f"상품 1개당 포스터 초안은 최대 {MAX_POSTERS_PER_PRODUCT}개까지 만들 수 있습니다. 기존 포스터를 삭제한 뒤 다시 생성해 주세요.",
        )


def _generate_poster_background(poster_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        poster = db.get(models.PosterAsset, poster_id)
        if not poster or poster.status not in ACTIVE_POSTER_STATUSES:
            return
        try:
            input_images = list(poster.input_images or []) if poster.input_images else []
            generated = generate_poster_image(
                prompt=poster.prompt,
                settings=settings,
                input_images=input_images if input_images else None,
            )
            image_path = _save_poster_file(
                asset_dir=Path(settings.poster_asset_dir),
                poster_id=poster.id,
                image_bytes=generated.image_bytes,
            )
            poster.status = "succeeded"
            poster.image_path = str(image_path)
            poster.image_url = f"/api/posters/{poster.id}/download"
            poster.provider_response_summary = {
                **(poster.provider_response_summary or {}),
                **generated.provider_response_summary,
            }
            poster.cost_usd = generated.cost_usd
            poster.latency_ms = generated.latency_ms
            poster.error = None
            poster.updated_at = models.utcnow()
            db.commit()
            db.refresh(poster)
            _log_poster_usage(poster, settings)
        except PosterImageGenerationError as exc:
            _mark_poster_failed(db, poster, exc.args[0], exc.details)
            _log_poster_usage(poster, settings)
        except OSError as exc:
            _mark_poster_failed(
                db,
                poster,
                "Poster image file could not be saved.",
                {"reason": "poster_file_save_failed", "error": str(exc)},
            )
            _log_poster_usage(poster, settings)


def _save_poster_file(*, asset_dir: Path, poster_id: str, image_bytes: bytes) -> Path:
    asset_dir.mkdir(parents=True, exist_ok=True)
    path = asset_dir / f"{poster_id}.png"
    path.write_bytes(image_bytes)
    return path


def _delete_file_if_exists(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass


def _mark_poster_failed(
    db: Session,
    poster: models.PosterAsset,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    poster.status = "failed"
    poster.error = {"message": message, "details": details or {}}
    poster.updated_at = models.utcnow()
    db.commit()
    db.refresh(poster)


def _poster_read(poster: models.PosterAsset) -> dict[str, Any]:
    return PosterAssetRead.model_validate(poster).model_dump(mode="json")


def _log_poster_usage(poster: models.PosterAsset, settings: Settings) -> None:
    safe_write_poster_usage_log(
        poster_id=poster.id,
        run_id=poster.run_id,
        product_id=poster.product_id,
        status=poster.status,
        provider=poster.provider,
        model=poster.image_model,
        style_preset=poster.style_preset,
        image_size=poster.image_size,
        image_quality=poster.image_quality,
        latency_ms=poster.latency_ms,
        cost_usd=float(poster.cost_usd or 0),
        provider_response_summary=poster.provider_response_summary,
        error=poster.error,
        settings=settings,
    )


def _log_poster_prompt(poster: models.PosterAsset, settings: Settings) -> None:
    summary = poster.provider_response_summary if isinstance(poster.provider_response_summary, dict) else {}
    prompt_source = summary.get("prompt_source") if isinstance(summary.get("prompt_source"), dict) else {}
    safe_write_poster_prompt_log(
        poster_id=poster.id,
        run_id=poster.run_id,
        product_id=poster.product_id,
        product_title=poster.product_title,
        style_preset=poster.style_preset,
        included_sections=list(poster.included_sections or []),
        prompt=poster.prompt,
        prompt_language=poster.prompt_language,
        image_model=poster.image_model,
        image_size=poster.image_size,
        image_quality=poster.image_quality,
        input_images=list(poster.input_images or []),
        prompt_source=prompt_source,
        settings=settings,
    )


def _is_evaluation_run(run: models.WorkflowRun | None) -> bool:
    if not run or not isinstance(run.input, dict):
        return False
    return isinstance(run.input.get("_evaluation"), dict)


def _download_filename(poster: models.PosterAsset) -> str:
    product_id = _filename_part(poster.product_id)
    run_id = _filename_part(poster.run_id)
    style = _filename_part(poster.style_preset)
    return f"paravoca_{run_id}_{product_id}_{style}.png"


def _filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return cleaned[:80] or "poster"
