from .base import CategoryKnowledge, MarginRange, ShippingProfile


class GuitarsCategory(CategoryKnowledge):
    name = slug = "guitars"
    description = "Electric, acoustic, bass, and effects gear."
    brands = (
        "Fender",
        "Gibson",
        "Martin",
        "Taylor",
        "PRS",
        "Ibanez",
        "Yamaha",
        "Epiphone",
        "Gretsch",
        "Marshall",
        "Mesa Boogie",
    )
    keywords = (
        "guitar",
        "bass",
        "amp",
        "amplifier",
        "pedal",
        "stratocaster",
        "telecaster",
        "les paul",
        "acoustic guitar",
        "effects pedal",
        "guitar case",
    )
    common_misspellings = ("strat", "gibsun", "fendre", "acustic")
    seasonality = "Gift demand rises in November–December; student instruments peak before fall term."
    repair_opportunities = (
        "setup and intonation",
        "fret leveling",
        "potentiometer cleaning",
        "amp tube testing",
    )
    shipping_profile = ShippingProfile(
        "oversize",
        "guitar box or local pickup",
        "Insure neck/headstock; humidity and impact damage are common.",
    )
    typical_margins = MarginRange(0.20, 0.45)
    pricing_providers = (
        "Reverb price guide",
        "eBay sold listings",
        "Guitar Center used",
    )
    common_model_prefixes = ("Stratocaster", "Telecaster", "Les Paul", "SG", "D-28")
    related_categories = ("audio", "collectibles", "books-media")
