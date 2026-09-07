from .base import CategoryKnowledge, MarginRange, ShippingProfile


class AudioCategory(CategoryKnowledge):
    name = slug = "audio"
    description = "Hi-fi, pro audio, speakers, turntables, and headphones."
    brands = (
        "Marantz",
        "Pioneer",
        "Technics",
        "Bose",
        "Yamaha",
        "Denon",
        "Klipsch",
        "Sennheiser",
        "McIntosh",
        "NAD",
        "Onkyo",
        "Shure",
    )
    keywords = (
        "receiver",
        "turntable",
        "speaker",
        "amplifier",
        "headphones",
        "mixer",
        "microphone",
        "subwoofer",
        "dac",
        "equalizer",
        "phono preamp",
        "soundbar",
    )
    common_misspellings = ("maranz", "senheiser", "technics", "sub woofer", "mckintosh")
    seasonality = "Holiday gifting benefits headphones; vintage hi-fi has steady enthusiast demand."
    repair_opportunities = (
        "refoam drivers",
        "capacitor recap",
        "belt replacement",
        "contact cleaning",
    )
    shipping_profile = ShippingProfile(
        "medium",
        "double-boxed insured parcel",
        "Protect cones and platters; oversized speakers are often local-pickup candidates.",
    )
    typical_margins = MarginRange(0.25, 0.55)
    pricing_providers = ("eBay sold listings", "HiFi Shark", "Reverb")
    common_model_prefixes = ("SL-", "PM", "AVR-", "WH-")
    related_categories = ("guitars", "electronics", "books-media")
