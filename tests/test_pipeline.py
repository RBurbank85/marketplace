import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock

from core.pipeline import PipelineEngine, PipelineContext, StageRegistry
from core.pipeline_stages import (
    ListingPipelineData,
    NormalizeStage,
    ValidateStage,
    PersistStage,
)
from database.schemas import ListingCreate


@pytest.mark.asyncio
async def test_pipeline_execution_flow():
    # Setup mock stages
    stage1 = MagicMock(spec=NormalizeStage)
    stage1.name = "normalize"
    
    async def side_effect(ctx):
        ctx.data.listing = ListingCreate(
            title="Test Listing",
            price=100.0,
            source="test",
            external_id="test-1"
        )
        return ctx
    
    stage1.process.side_effect = side_effect
    
    stage2 = MagicMock(spec=ValidateStage)
    stage2.name = "validate"
    stage2.process.side_effect = lambda ctx: ctx
    
    engine = PipelineEngine([stage1, stage2])
    raw_data = {"title": "Test Listing", "price": "100.0", "source": "test"}
    data = ListingPipelineData(raw_data=raw_data)
    
    context = await engine.execute(data)
    
    assert context.data.listing is not None
    assert context.data.listing.title == "Test Listing"
    assert len(context.metrics) == 2
    assert context.metrics[0].stage_name == "normalize"
    assert context.metrics[0].success is True


@pytest.mark.asyncio
async def test_pipeline_termination():
    stage1 = MagicMock(spec=NormalizeStage)
    stage1.name = "normalize"
    
    async def side_effect(ctx):
        ctx.terminate("Test termination")
        return ctx
    stage1.process.side_effect = side_effect
    
    stage2 = MagicMock(spec=ValidateStage)
    stage2.name = "validate"
    
    engine = PipelineEngine([stage1, stage2])
    data = ListingPipelineData(raw_data={})
    
    context = await engine.execute(data)
    
    assert context.terminated is True
    assert context.termination_reason == "Test termination"
    # Stage 2 should not have been executed
    assert len(context.metrics) == 1
    stage2.process.assert_not_called()


def test_stage_registry():
    assert StageRegistry.get("normalize") is NormalizeStage
    assert StageRegistry.get("validate") is ValidateStage
    assert StageRegistry.get("persist") is PersistStage


def test_pipeline_from_config():
    config = [
        "normalize",
        "validate",
        {"persist": {"name": "custom_persist"}}
    ]
    engine = PipelineEngine.from_config(config)
    
    assert len(engine.stages) == 3
    assert isinstance(engine.stages[0], NormalizeStage)
    assert isinstance(engine.stages[1], ValidateStage)
    assert isinstance(engine.stages[2], PersistStage)
    assert engine.stages[2].name == "custom_persist"


@pytest.mark.asyncio
async def test_normalize_stage_logic():
    stage = NormalizeStage()
    data = ListingPipelineData(raw_data={
        "title": "  Nintendo Switch  ",
        "price": "$299,99",
        "source": "craigslist",
        "url": "http://example.com/1"
    })
    context = PipelineContext(data=data)
    
    result_context = await stage.process(context)
    listing = result_context.data.listing
    
    assert listing.title == "Nintendo Switch"
    assert listing.price == 299.99
    assert listing.source == "craigslist"
    assert listing.external_id == "http://example.com/1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_price", "expected_price"),
    [
        (299.99, 299.99),
        ("$299.99", 299.99),
        ("$1,299.99", 1299.99),
        ("$299,99", 299.99),
        ("  $299.99  ", 299.99),
    ],
)
async def test_normalize_stage_price_formats(raw_price, expected_price):
    context = PipelineContext(
        data=ListingPipelineData(
            raw_data={"title": "Test Listing", "price": raw_price, "source": "test"}
        )
    )

    result_context = await NormalizeStage().process(context)

    assert result_context.data.listing.price == expected_price


@pytest.mark.asyncio
async def test_normalize_stage_invalid_price_preserves_pydantic_validation():
    context = PipelineContext(
        data=ListingPipelineData(
            raw_data={"title": "Test Listing", "price": "not-a-price", "source": "test"}
        )
    )

    with pytest.raises(ValidationError):
        await NormalizeStage().process(context)


@pytest.mark.asyncio
async def test_validate_stage_failure():
    stage = ValidateStage()
    # Missing title and invalid price
    data = ListingPipelineData(listing=ListingCreate(title="", price=0, source="test"))
    context = PipelineContext(data=data)
    
    result_context = await stage.process(context)
    
    assert result_context.terminated is True
    assert "Validation failed" in result_context.termination_reason
    assert "Title is missing" in result_context.data.validation_errors
    assert "Price must be greater than zero" in result_context.data.validation_errors
