from .base import CategoryKnowledge, MarginRange, ShippingProfile


class AutoPartsCategory(CategoryKnowledge):
    name = slug = "auto-parts"
    description = "OEM and aftermarket vehicle parts, accessories, diagnostics, and service components."
    brands = ("ACDelco", "Bosch", "Denso", "Ford", "GM", "Honda", "Mopar", "Toyota")
    keywords = ("alternator", "bumper", "carburetor", "ecu", "headlight", "oem", "taillight", "turbo")
    common_misspellings = ("after market", "break pads", "carborator", "tail light")
    seasonality = "Maintenance demand is steady; tires, lighting, cooling, and 4x4 parts rise with weather and travel seasons."
    repair_opportunities = ("connector repair", "lens restoration", "motor testing", "part-number verification")
    shipping_profile = ShippingProfile("medium", "insured ground parcel or freight", "Confirm exact fitment, side, condition, and hazardous-material restrictions before listing.")
    typical_margins = MarginRange(0.20, 0.55)
    pricing_providers = ("eBay sold listings", "RockAuto", "Car-Part.com")
    common_model_prefixes = ("ACDelco", "Dorman", "Motorcraft", "OEM")
    related_categories = ("power-tools", "industrial", "electronics")
