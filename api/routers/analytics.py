from typing import Any, Callable, List

from fastapi import APIRouter, HTTPException
from analytics import queries
from analytics.warehouse import sync_operational_data
from config.settings import settings

router = APIRouter(prefix="/analytics", tags=["analytics"])

SNAPSHOT_REQUIRED_CODE = "analytics_snapshot_required"
SNAPSHOT_REQUIRED_MESSAGE = (
    "Analytics data is not available yet. Run 'maie analytics sync' and try again."
)


def _read(query: Callable[..., Any]) -> Any:
    try:
        return query(settings.analytics_warehouse_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": SNAPSHOT_REQUIRED_CODE, "message": SNAPSHOT_REQUIRED_MESSAGE},
        ) from exc


@router.post("/sync")
def sync_analytics() -> dict[str, Any]:
    metrics = sync_operational_data(
        operational_path=settings.sqlite_path,
        warehouse_path=settings.analytics_warehouse_path,
    )
    return {
        "warehouse_path": str(settings.analytics_warehouse_path),
        "tables": metrics.tables,
        "duration_seconds": metrics.duration_seconds,
    }


@router.get("/most-profitable-categories", response_model=List[dict])
def get_most_profitable_categories() -> Any:
    return _read(queries.most_profitable_categories)


@router.get("/average-flipscore", response_model=List[dict])
def get_average_flipscore() -> Any:
    return _read(queries.average_flipscore)


@router.get("/median-asking-prices", response_model=List[dict])
def get_median_asking_prices() -> Any:
    return _read(queries.median_asking_prices)


@router.get("/price-reductions", response_model=List[dict])
def get_price_reductions() -> Any:
    return _read(queries.price_reductions)


@router.get("/seller-frequency", response_model=List[dict])
def get_seller_frequency() -> Any:
    return _read(queries.seller_frequency)


@router.get("/keyword-performance", response_model=List[dict])
def get_keyword_performance() -> Any:
    return _read(queries.keyword_performance)


@router.get("/category-trends", response_model=List[dict])
def get_category_trends() -> Any:
    return _read(queries.category_trends)


@router.get("/daily-listing-volume", response_model=List[dict])
def get_daily_listing_volume() -> Any:
    return _read(queries.daily_listing_volume)
