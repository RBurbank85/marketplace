from .base import CategoryKnowledge, MarginRange, ShippingProfile


class IndustrialCategory(CategoryKnowledge):
    name = slug = "industrial"
    description = "Industrial controls, machining, automation, and test equipment."
    brands = (
        "Siemens",
        "Allen-Bradley",
        "ABB",
        "Fanuc",
        "Omron",
        "Fluke",
        "Haas",
        "Mitsubishi",
        "Keyence",
        "Schneider Electric",
        "Yaskawa",
    )
    keywords = (
        "plc",
        "vfd",
        "servo",
        "hmi",
        "cnc",
        "welding",
        "compressor",
        "oscilloscope",
        "actuator",
        "encoder",
        "motion control",
        "power supply",
    )
    common_misspellings = (
        "allen bradley",
        "mitsu",
        "osciloscope",
        "variabel frequency drive",
    )
    seasonality = "Stable year-round; plant shutdowns and capital-budget windows create liquidation opportunities."
    repair_opportunities = (
        "terminal cleanup",
        "capacitor replacement",
        "calibration",
        "bearing replacement",
    )
    shipping_profile = ShippingProfile(
        "heavy",
        "crated freight or foam-packed parcel",
        "Record part numbers and protect connectors; verify hazardous-material handling.",
    )
    typical_margins = MarginRange(0.30, 0.65)
    pricing_providers = ("eBay sold listings", "Radwell", "EquipNet")
    common_model_prefixes = ("1756-", "6ES7", "A06B", "525-")
    related_categories = ("servers", "medical", "office-equipment", "auto-parts")
