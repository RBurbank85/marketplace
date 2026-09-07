from .base import CategoryKnowledge, MarginRange, ShippingProfile


class CamerasCategory(CategoryKnowledge):
    name = slug = "cameras"
    description = "Interchangeable-lens cameras, lenses, and video equipment."
    brands = (
        "Canon",
        "Nikon",
        "Sony",
        "Fujifilm",
        "Olympus",
        "Panasonic",
        "Leica",
        "DJI",
        "GoPro",
        "Sigma",
        "Tamron",
    )
    keywords = (
        "camera",
        "lens",
        "dslr",
        "mirrorless",
        "shutter count",
        "tripod",
        "camcorder",
        "gimbal",
        "film camera",
        "flash",
        "rangefinder",
    )
    common_misspellings = ("cannon", "nikon", "fujii", "mirorless")
    seasonality = "Demand peaks before summer travel and holiday gifting; wedding season supports lenses."
    repair_opportunities = (
        "sensor cleaning",
        "rubber grip replacement",
        "battery-door repair",
        "fungus inspection",
    )
    shipping_profile = ShippingProfile(
        "small",
        "padded insured parcel",
        "Photograph serials and protect optics from impact and moisture.",
    )
    typical_margins = MarginRange(0.20, 0.50)
    pricing_providers = ("eBay sold listings", "MPB", "KEH Camera")
    common_model_prefixes = ("EOS", "Alpha", "Z", "X-T", "D850")
    related_categories = ("electronics", "drones", "sporting-goods")
