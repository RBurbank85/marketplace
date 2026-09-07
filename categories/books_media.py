from .base import CategoryKnowledge, MarginRange, ShippingProfile


class BooksMediaCategory(CategoryKnowledge):
    name = slug = "books-media"
    description = "Out-of-print books, boxed sets, physical media, manuals, and niche reference material."
    brands = ("Barnes & Noble", "Criterion", "DC Comics", "Marvel", "Nintendo Power", "Scholastic", "The Folio Society", "VHS")
    keywords = ("blu-ray", "book set", "first edition", "hardcover", "manual", "manga", "out of print", "vinyl")
    common_misspellings = ("blu ray", "first edtion", "hard cover", "outofprint")
    seasonality = "Textbooks lift around academic terms; giftable sets and media lift in Q4; scarce reference titles sell year-round."
    repair_opportunities = ("disc resurfacing", "dust-jacket protection", "light cleaning", "page-count verification")
    shipping_profile = ShippingProfile("small", "rigid mailer or boxed media parcel", "State edition, ISBN, completeness, region code, and condition; pack corners and discs against damage.")
    typical_margins = MarginRange(0.20, 0.65)
    pricing_providers = ("eBay sold listings", "AbeBooks", "Discogs")
    common_model_prefixes = ("ISBN", "Criterion", "OOP", "VHS")
    related_categories = ("collectibles", "gaming", "audio")
