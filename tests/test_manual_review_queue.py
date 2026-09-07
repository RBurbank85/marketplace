from __future__ import annotations

from uuid import uuid4

from typer.testing import CliRunner

from app.main import app
from database.database import initialize_database
from database.models import Listing, Opportunity, Queue, QueueStatus
from database.repositories import (
    ListingRepository,
    OpportunityRepository,
    QueueRepository,
)


def _queue_item(database_url: str) -> Queue:
    listing = ListingRepository(database_url).create(
        Listing(title="Camera", price=100.0, source="test", external_id="camera-1")
    )
    opportunity = OpportunityRepository(database_url).create(
        Opportunity(potential_profit=50.0, confidence_score=0.9, listing_id=listing.id)
    )
    item = QueueRepository(database_url).list()
    assert len(item) == 1
    assert item[0].opportunity_id == opportunity.id
    return item[0]


def test_queue_repository_tracks_manual_review_lifecycle(tmp_path) -> None:
    database_url = str(tmp_path / "queue.db")
    initialize_database(database_url)
    item = _queue_item(database_url)
    repository = QueueRepository(database_url)

    assert repository.list_by_status(QueueStatus.NEW) == [item]

    reviewing = repository.review(item.id, "Checking condition")
    assert reviewing is not None
    assert reviewing.status == QueueStatus.REVIEWING
    assert reviewing.reviewed_at is not None
    assert reviewing.review_notes == "Checking condition"

    approved = repository.approve(item.id, "Verified")
    assert approved is not None
    assert approved.status == QueueStatus.APPROVED
    assert approved.review_notes == "Verified"

    rejected = repository.reject(item.id, "Changed my mind")
    assert rejected is not None
    assert rejected.status == QueueStatus.REJECTED

    archived = repository.archive(item.id)
    assert archived is not None
    assert archived.status == QueueStatus.ARCHIVED


def test_queue_repository_accepts_string_ids_and_handles_missing_items(tmp_path) -> None:
    database_url = str(tmp_path / "queue-string-id.db")
    initialize_database(database_url)
    item = _queue_item(database_url)
    repository = QueueRepository(database_url)

    reviewing = repository.review(str(item.id), "Checking condition")
    assert reviewing is not None
    assert reviewing.status == QueueStatus.REVIEWING

    assert repository.review(str(uuid4())) is None
    repository.delete(str(item.id))
    assert repository.get_by_id(item.id) is None


def test_queue_cli_lists_and_transitions_items(tmp_path) -> None:
    database_url = str(tmp_path / "queue-cli.db")
    initialize_database(database_url)
    item = _queue_item(database_url)
    runner = CliRunner()

    listed = runner.invoke(app, ["queue", "list", "--database-url", database_url])
    assert listed.exit_code == 0
    assert str(item.id) in listed.output
    assert "new" in listed.output

    reviewing = runner.invoke(
        app,
        [
            "queue",
            "review",
            str(item.id),
            "--notes",
            "Inspecting",
            "--database-url",
            database_url,
        ],
    )
    assert reviewing.exit_code == 0
    assert "reviewing" in reviewing.output

    approved = runner.invoke(
        app, ["queue", "approve", str(item.id), "--database-url", database_url]
    )
    assert approved.exit_code == 0
    assert "approved" in approved.output


def test_queue_cli_reports_missing_item(tmp_path) -> None:
    database_url = str(tmp_path / "missing-queue.db")
    initialize_database(database_url)

    result = CliRunner().invoke(
        app,
        [
            "queue",
            "archive",
            "00000000-0000-0000-0000-000000000000",
            "--database-url",
            database_url,
        ],
    )

    assert result.exit_code == 1
    assert "Queue item not found" in result.output
