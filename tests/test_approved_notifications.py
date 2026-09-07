from __future__ import annotations

from alerts.notifications import AlertNotification, Notification, NotificationService
from database.database import initialize_database
from database.models import Listing, Opportunity, QueueStatus
from database.repositories import (
    ListingRepository,
    NotificationDeliveryRepository,
    OpportunityRepository,
    QueueRepository,
    QueueTransitionError,
    StaleQueueUpdateError,
)
from alerts.approval import ApprovedOpportunityDispatcher
from api import deps
from api.main import app
from config.settings import settings
import pytest
from fastapi.testclient import TestClient
from api.deps import get_db
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool


class RecordingProvider(Notification):
    name = "recording"

    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.alerts: list[AlertNotification] = []

    def send(self, alert: AlertNotification) -> None:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("provider unavailable")
        self.alerts.append(alert)


def _approved_item(database_url: str):
    listing = ListingRepository(database_url).create(
        Listing(
            title="Camera",
            price=100,
            source="test",
            external_id="camera-notify",
            url="https://example.test/camera",
            flip_score=88,
        )
    )
    opportunity = OpportunityRepository(database_url).create(
        Opportunity(
            listing_id=listing.id,
            potential_profit=50,
            confidence_score=0.9,
            estimated_market_value=150,
            flip_score=88,
            notes="Strong margin",
        )
    )
    queue = QueueRepository(database_url)
    item = queue.get_for_opportunity(opportunity.id)
    queue.review(item.id)
    return queue.approve(item.id)


def test_approved_dispatch_is_deduplicated_per_provider(tmp_path) -> None:
    database_url = str(tmp_path / "approved.db")
    initialize_database(database_url)
    item = _approved_item(database_url)
    first = RecordingProvider()
    second = RecordingProvider()
    second.name = "second-recording"
    dispatcher = ApprovedOpportunityDispatcher(
        NotificationService([first, second]), database_url=database_url
    )

    assert dispatcher.dispatch(item.id) == [
        {"provider": "recording", "status": "succeeded"},
        {"provider": "second-recording", "status": "succeeded"},
    ]
    assert dispatcher.dispatch(item.id) == [
        {"provider": "recording", "status": "succeeded"},
        {"provider": "second-recording", "status": "succeeded"},
    ]
    assert len(first.alerts) == 1
    assert len(second.alerts) == 1
    assert all(
        delivery.status == "succeeded"
        for delivery in NotificationDeliveryRepository(database_url).list()
    )


def test_failed_delivery_is_visible_and_retryable(tmp_path) -> None:
    database_url = str(tmp_path / "retry.db")
    initialize_database(database_url)
    item = _approved_item(database_url)
    provider = RecordingProvider(failures=1)
    dispatcher = ApprovedOpportunityDispatcher(
        NotificationService([provider]), database_url=database_url
    )

    assert dispatcher.dispatch(item.id)[0]["status"] == "failed"
    failed = NotificationDeliveryRepository(database_url).list()[0]
    assert failed.status == "failed"
    assert failed.error == "provider unavailable"

    assert dispatcher.dispatch(item.id)[0]["status"] == "succeeded"
    assert len(provider.alerts) == 1


def test_rejected_and_archived_items_cannot_notify(tmp_path) -> None:
    database_url = str(tmp_path / "not-approved.db")
    initialize_database(database_url)
    listing = ListingRepository(database_url).create(
        Listing(title="Camera", price=100, source="test", external_id="camera-reject")
    )
    opportunity = OpportunityRepository(database_url).create(
        Opportunity(listing_id=listing.id, potential_profit=50, confidence_score=0.9)
    )
    queue = QueueRepository(database_url)
    item = queue.get_for_opportunity(opportunity.id)
    queue.review(item.id)
    queue.reject(item.id)

    dispatcher = ApprovedOpportunityDispatcher(
        NotificationService([RecordingProvider()]), database_url=database_url
    )
    try:
        dispatcher.dispatch(item.id)
    except QueueTransitionError as exc:
        assert "approved" in str(exc)
    else:
        raise AssertionError("rejected item was dispatched")
    assert NotificationDeliveryRepository(database_url).list() == []


def test_queue_transitions_reject_invalid_and_stale_updates(tmp_path) -> None:
    database_url = str(tmp_path / "transitions.db")
    initialize_database(database_url)
    item = _approved_item(database_url)
    queue = QueueRepository(database_url)

    new_listing = ListingRepository(database_url).create(
        Listing(title="Lens", price=40, source="test", external_id="lens-transition")
    )
    new_opportunity = OpportunityRepository(database_url).create(
        Opportunity(listing_id=new_listing.id, potential_profit=20, confidence_score=0.8)
    )
    new_item = queue.get_for_opportunity(new_opportunity.id)
    try:
        queue.approve(new_item.id, expected_version=new_item.version)
    except QueueTransitionError:
        pass
    else:
        raise AssertionError("new transition was unexpectedly accepted")

    stale = item.version - 1
    try:
        queue.approve(item.id, expected_version=stale)
    except StaleQueueUpdateError:
        pass
    else:
        raise AssertionError("stale transition was unexpectedly accepted")

    assert queue.get_by_id(item.id).status == QueueStatus.APPROVED


@pytest.fixture
def api_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def api_client(api_session):
    def get_db_override():
        return api_session

    app.dependency_overrides[get_db] = get_db_override
    client = TestClient(app, headers={"X-API-Key": settings.api_key or ""})
    yield client
    app.dependency_overrides.clear()


def test_api_approval_requires_version_and_reports_delivery(api_client, api_session) -> None:
    listing = ListingRepository(session=api_session).create(
        Listing(title="API camera", price=100, source="test", external_id="api-camera")
    )
    opportunity = OpportunityRepository(session=api_session).create(
        Opportunity(listing_id=listing.id, potential_profit=50, confidence_score=0.9)
    )
    queue = QueueRepository(session=api_session)
    item = queue.get_for_opportunity(opportunity.id)
    provider = RecordingProvider()
    app.dependency_overrides[deps.get_notification_service] = lambda: NotificationService(
        [provider]
    )

    reviewed = api_client.post(
        f"/queue/{item.id}/review", json={"expected_version": item.version}
    )
    assert reviewed.status_code == 200
    approved = api_client.post(
        f"/queue/{item.id}/approve",
        json={"expected_version": reviewed.json()["version"]},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["notification_results"] == [
        {"provider": "recording", "status": "succeeded"}
    ]
    assert len(provider.alerts) == 1
