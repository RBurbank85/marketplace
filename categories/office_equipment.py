from .base import CategoryKnowledge, MarginRange, ShippingProfile


class OfficeEquipmentCategory(CategoryKnowledge):
    name = slug = "office-equipment"
    description = "Business printers, scanners, label makers, point-of-sale, and document-processing equipment."
    brands = ("Brother", "Canon", "Dymo", "Epson", "Fujitsu", "HP", "Star Micronics", "Zebra")
    keywords = ("barcode", "label printer", "pos", "receipt printer", "scanner", "shredder", "thermal", "toner")
    common_misspellings = ("bar code", "dyemo", "lable printer", "reciept printer")
    seasonality = "Small-business setup and school cycles create demand, while replacement labels, scanners, and POS hardware move year-round."
    repair_opportunities = ("feed-roller cleaning", "firmware reset", "printhead cleaning", "power-supply testing")
    shipping_profile = ShippingProfile("medium", "foam-packed insured parcel", "Test with a sample print or scan, remove consumables as appropriate, and record counters or serials.")
    typical_margins = MarginRange(0.20, 0.55)
    pricing_providers = ("eBay sold listings", "Amazon sold offers", "Facebook Marketplace")
    common_model_prefixes = ("DS", "QL", "TM-", "ZD")
    related_categories = ("electronics", "networking", "industrial")
