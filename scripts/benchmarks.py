import time
import asyncio

from analysis.flipscore import evaluate_listing
from collectors.parsers.craigslist import CraigslistParser
from analysis.keywords import keyword_score
from database.repositories import ListingRepository
from database.models import Listing, ListingStatus
from database.database import initialize_database

def benchmark_scoring(n: int = 100):
    listing = {
        "title": "Vintage Sony Camera",
        "description": "Works great, minor scratches. Must sell!",
        "price": 250.0,
        "category": "cameras",
        "distance": 10.0,
        "view_count": 50,
    }
    
    start = time.perf_counter()
    for _ in range(n):
        evaluate_listing(listing)
    end = time.perf_counter()
    
    avg = (end - start) / n
    print(f"Scoring Benchmark (n={n}): Average {avg*1000:.4f}ms per listing")

def benchmark_parsing(n: int = 100):
    with open("tests/fixtures/craigslist_search.html") as f:
        html = f.read()
    
    parser = CraigslistParser()
    
    start = time.perf_counter()
    for _ in range(n):
        parser.parse(html)
    end = time.perf_counter()
    
    avg = (end - start) / n
    print(f"Parsing Benchmark (n={n}): Average {avg*1000:.4f}ms per file")

def benchmark_keywords(n: int = 1000):
    text = "Vintage Sony Camera. Works great, minor scratches. Must sell! Needs work."
    
    # Warm up cache
    keyword_score(text)
    
    start = time.perf_counter()
    for _ in range(n):
        keyword_score(text)
    end = time.perf_counter()
    
    avg = (end - start) / n
    print(f"Keyword Score Benchmark (cached, n={n}): Average {avg*1000000:.4f}us per call")

async def benchmark_database_bulk(n: int = 1000):
    db_path = "benchmark_test.db"
    db_url = f"sqlite:///{db_path}"
    initialize_database(db_url)
    repo = ListingRepository(db_url)
    
    listings = [
        Listing(
            title=f"Item {i}",
            price=10.0 * i,
            source="test",
            external_id=f"ext_{i}",
            url=f"http://example.com/{i}",
            status=ListingStatus.NEW
        )
        for i in range(n)
    ]
    
    start = time.perf_counter()
    repo.bulk_create(listings)
    end = time.perf_counter()
    
    print(f"Database Bulk Create Benchmark (n={n}): Total {end-start:.4f}s ({((end-start)/n)*1000:.4f}ms per record)")
    
    import os
    if os.path.exists(db_path):
        os.remove(db_path)

async def main():
    print("--- Performance Benchmarks ---")
    benchmark_scoring()
    benchmark_parsing()
    benchmark_keywords()
    await benchmark_database_bulk()

if __name__ == "__main__":
    asyncio.run(main())
