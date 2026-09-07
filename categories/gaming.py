from .base import CategoryKnowledge, MarginRange, ShippingProfile


class GamingCategory(CategoryKnowledge):
    name = slug = "gaming"
    description = "Game consoles, handhelds, games, and accessories."
    brands = ("Nintendo", "Sony", "Microsoft", "Valve", "Sega", "Atari", "Analogue", "Meta")
    keywords = (
        "playstation",
        "xbox",
        "nintendo",
        "switch",
        "gamecube",
        "console",
        "controller",
        "game boy",
        "handheld",
        "retro game",
        "vr headset",
    )
    common_misspellings = ("nintindo", "play station", "x box", "nintendoe")
    seasonality = "Holiday and back-to-school demand are strongest; collectible titles move year-round."
    repair_opportunities = (
        "stick-drift repair",
        "disc-drive cleaning",
        "shell replacement",
        "battery replacement",
    )
    shipping_profile = ShippingProfile(
        "small",
        "tracked parcel with insurance",
        "Test controllers, remove accounts, and document serial numbers.",
    )
    typical_margins = MarginRange(0.25, 0.55)
    pricing_providers = ("eBay sold listings", "PriceCharting", "GameStop trade values")
    common_model_prefixes = ("PS", "Xbox", "Switch", "Game Boy", "Steam Deck")
    related_categories = ("electronics", "collectibles", "books-media")
