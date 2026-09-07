from .base import CategoryKnowledge, MarginRange, ShippingProfile


class LabEquipmentCategory(CategoryKnowledge):
    name = slug = "lab-equipment"
    description = "Scientific laboratory instruments and analytical equipment."
    brands = (
        "Thermo Fisher",
        "Agilent",
        "Eppendorf",
        "Bio-Rad",
        "VWR",
        "Mettler Toledo",
        "Shimadzu",
        "Bruker",
        "Waters",
    )
    keywords = (
        "pipette",
        "centrifuge",
        "incubator",
        "spectrometer",
        "chromatograph",
        "microscope",
        "balance",
        "freezer",
        "pcr",
        "vortex mixer",
    )
    common_misspellings = (
        "ependorf",
        "centrifuge",
        "spectrophotometer",
        "chromotograph",
    )
    seasonality = "University surplus is common after academic terms; research procurement runs year-round."
    repair_opportunities = (
        "calibration",
        "lamp replacement",
        "seal replacement",
        "motor service",
    )
    shipping_profile = ShippingProfile(
        "specialized",
        "foam-packed freight or insured parcel",
        "Require decontamination documentation and protect sensitive optics.",
    )
    typical_margins = MarginRange(0.30, 0.65)
    pricing_providers = ("eBay sold listings", "LabX", "EquipNet")
    common_model_prefixes = ("Sorvall", "Pipetman", "NanoDrop", "Cary")
    related_categories = ("medical", "industrial", "office-equipment")
