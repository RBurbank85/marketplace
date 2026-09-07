from __future__ import annotations


from database.database import initialize_database
from database.models import (
    Listing,
    ListingStatus,
    Opportunity,
    PriceHistory,
    Purchase,
    Search,
    Seller,
)
from database.repositories import (
    ListingRepository,
    OpportunityRepository,
    PriceHistoryRepository,
    PurchaseRepository,
    SearchRepository,
    SellerRepository,
)


def _create_listing_record(database_url: str) -> Listing:
    from sqlmodel import Session

    from database.database import get_engine

    with Session(get_engine(database_url)) as session:
        seller = Seller(name="Test Seller", username="seller1", rating=4.8)
        search = Search(query="nintendo switch", source="ebay")
        listing = Listing(
            title="Nintendo Switch OLED",
            description="Great condition",
            price=299.99,
            source="ebay",
            external_id="listing-0001",
            seller=seller,
            search=search,
            status=ListingStatus.NEW,
        )
        session.add_all([seller, search, listing])
        session.commit()
        session.refresh(listing)
        return listing


def test_seller_repository_crud(tmp_path) -> None:
    db_path = tmp_path / "sellers.db"
    initialize_database(str(db_path))

    repo = SellerRepository(database_url=str(db_path))
    seller = repo.create(Seller(name="Seller One", username="seller-one", rating=4.7))

    fetched = repo.get_by_id(seller.id)
    assert fetched is not None
    assert fetched.name == "Seller One"

    updated = repo.update(seller.id, {"rating": 4.9})
    assert updated is not None
    assert updated.rating == 4.9

    assert len(repo.list()) == 1
    repo.delete(seller.id)
    assert repo.get_by_id(seller.id) is None


def test_search_repository_crud(tmp_path) -> None:
    db_path = tmp_path / "searches.db"
    initialize_database(str(db_path))

    repo = SearchRepository(database_url=str(db_path))
    search = repo.create(Search(query="iphone 15", source="craigslist", location="SF"))

    fetched = repo.get_by_id(search.id)
    assert fetched is not None
    assert fetched.query == "iphone 15"

    updated = repo.update(search.id, {"location": "Oakland"})
    assert updated is not None
    assert updated.location == "Oakland"

    assert len(repo.list()) == 1
    repo.delete(search.id)
    assert repo.get_by_id(search.id) is None


def test_listing_repository_crud(tmp_path) -> None:
    db_path = tmp_path / "listings.db"
    initialize_database(str(db_path))

    repo = ListingRepository(database_url=str(db_path))
    listing = repo.create(
        Listing(
            title="PS5 Slim",
            description="Disc version",
            price=449.0,
            source="offerup",
            external_id="ps5-001",
            status=ListingStatus.WATCHING,
        )
    )

    fetched = repo.get_by_id(listing.id)
    assert fetched is not None
    assert fetched.title == "PS5 Slim"

    updated = repo.update(listing.id, {"price": 399.0})
    assert updated is not None
    assert updated.price == 399.0

    assert len(repo.list()) == 1
    repo.delete(listing.id)
    assert repo.get_by_id(listing.id) is None


def test_price_history_repository_tracks_listing_history(tmp_path) -> None:
    db_path = tmp_path / "price-history.db"
    initialize_database(str(db_path))

    listing = _create_listing_record(str(db_path))
    repo = PriceHistoryRepository(database_url=str(db_path))

    entry = repo.create(PriceHistory(price=289.99, listing_id=listing.id))
    entries = repo.list_for_listing(listing.id)

    assert entry.price == 289.99
    assert len(entries) == 1
    assert entries[0].listing_id == listing.id


def test_purchase_repository_persists_purchase_record(tmp_path) -> None:
    db_path = tmp_path / "purchases.db"
    initialize_database(str(db_path))

    listing = _create_listing_record(str(db_path))
    repo = PurchaseRepository(database_url=str(db_path))

    repo.create(
        Purchase(price_paid=299.99, notes="Bought it", listing_id=listing.id)
    )

    fetched = repo.get_by_listing_id(listing.id)
    assert fetched is not None
    assert fetched.price_paid == 299.99
    assert fetched.notes == "Bought it"


def test_opportunity_repository_tracks_opportunities(tmp_path) -> None:
    db_path = tmp_path / "opportunities.db"
    initialize_database(str(db_path))

    listing = _create_listing_record(str(db_path))
    repo = OpportunityRepository(database_url=str(db_path))

    opportunity = repo.create(
        Opportunity(
            potential_profit=30.0,
            confidence_score=0.9,
            notes="Good margin",
            listing_id=listing.id,
        )
    )

    opportunities = repo.list_for_listing(listing.id)
    assert opportunity.listing_id == listing.id
    assert len(opportunities) == 1
    assert opportunities[0].confidence_score == 0.9
