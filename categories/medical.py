from .base import CategoryKnowledge, MarginRange, ShippingProfile


class MedicalCategory(CategoryKnowledge):
    name = slug = "medical"
    description = (
        "Non-restricted medical, dental, laboratory, and diagnostic equipment."
    )
    brands = (
        "GE Healthcare",
        "Philips",
        "Mindray",
        "Stryker",
        "Welch Allyn",
        "Zoll",
        "Beckman Coulter",
        "Hillrom",
        "Masimo",
    )
    keywords = (
        "ultrasound",
        "patient monitor",
        "centrifuge",
        "autoclave",
        "dental",
        "defibrillator",
        "microscope",
        "exam table",
        "infusion pump",
        "pulse oximeter",
        "surgical",
    )
    common_misspellings = ("ultra sound", "centrafuge", "defibulator", "welch allen")
    seasonality = "Budget-driven demand often rises near fiscal-year close; clinics purchase year-round."
    repair_opportunities = (
        "battery replacement",
        "probe inspection",
        "preventive maintenance",
        "calibration",
    )
    shipping_profile = ShippingProfile(
        "specialized",
        "insured freight or trained carrier",
        "Check regulations, decontamination records, recalls, and restricted-device rules.",
    )
    typical_margins = MarginRange(0.25, 0.60)
    pricing_providers = ("eBay sold listings", "DOTmed", "MedWOW")
    common_model_prefixes = ("LOGIQ", "SonoSite", "IntelliVue", "LifePak")
    related_categories = ("industrial", "lab-equipment", "office-equipment")
