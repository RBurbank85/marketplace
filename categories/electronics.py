from .base import CategoryKnowledge, MarginRange, ShippingProfile


class ElectronicsCategory(CategoryKnowledge):
    name = slug = "electronics"
    description = "Portable consumer electronics and smart devices."
    brands = ("Apple", "Samsung", "Google", "Microsoft", "Sony", "Bose")
    keywords = (
        "iphone",
        "ipad",
        "laptop",
        "phone",
        "headphone",
        "tablet",
        "smartwatch",
    )
    common_misspellings = ("iphon", "samsing", "mac book", "air pods")
    seasonality = (
        "Strong Q4 gifting demand; phones also move well around launch cycles."
    )
    seasonality_months = (11, 12)
    repair_opportunities = (
        "battery replacement",
        "screen replacement",
        "charging-port cleaning",
    )
    shipping_profile = ShippingProfile(
        "small",
        "tracked parcel with insurance",
        "Verify activation locks and lithium-battery rules.",
    )
    typical_margins = MarginRange(0.25, 0.45)
    pricing_providers = ("eBay sold listings", "Swappa", "Back Market")
    common_model_prefixes = ("iPhone", "iPad", "Galaxy", "Pixel", "Surface")
    related_categories = ("cameras", "audio", "gaming")
