from .base import CategoryKnowledge, MarginRange, ShippingProfile


class WatchesCategory(CategoryKnowledge):
    name = slug = "watches"
    description = "Mechanical, quartz, smart, and collectible watches."
    brands = (
        "Rolex",
        "Omega",
        "Seiko",
        "Hamilton",
        "Tissot",
        "Citizen",
        "Casio",
        "Tag Heuer",
        "Grand Seiko",
        "Longines",
        "Tudor",
    )
    keywords = (
        "watch",
        "chronograph",
        "automatic",
        "diver",
        "wristwatch",
        "bezel",
        "movement",
        "digital watch",
        "field watch",
        "watch band",
    )
    common_misspellings = ("rolexx", "omeaga", "seiko5", "tag heur")
    seasonality = "Gift demand peaks in Q4 and around graduations; vintage interest is year-round."
    repair_opportunities = (
        "battery replacement",
        "crystal replacement",
        "bracelet resizing",
        "movement service",
    )
    shipping_profile = ShippingProfile(
        "small",
        "signature-required insured parcel",
        "Authenticate high-value pieces and photograph serial/reference numbers.",
    )
    typical_margins = MarginRange(0.20, 0.60)
    pricing_providers = ("eBay sold listings", "Chrono24", "WatchCharts")
    common_model_prefixes = ("Datejust", "Speedmaster", "SRP", "G-Shock")
    related_categories = ("collectibles", "electronics", "jewelry", "fashion")
