from .base import CategoryKnowledge, MarginRange, ShippingProfile


class AppliancesCategory(CategoryKnowledge):
    name = slug = "appliances"
    description = "Countertop appliances, vacuum systems, coffee equipment, and replacement appliance parts."
    brands = ("Breville", "Dyson", "Jura", "Miele", "Ninja", "Shark", "Vitamix", "Zojirushi")
    keywords = ("blender", "coffee maker", "espresso machine", "food processor", "robot vacuum", "toaster", "vacuum", "water filter")
    common_misspellings = ("expresso", "food prossesor", "robot vaccuum", "zojirushi")
    seasonality = "Kitchen appliances rise during Q4; coffee and air-quality equipment see recurring replacement and seasonal demand."
    repair_opportunities = ("descaling", "filter replacement", "gasket replacement", "power-cord inspection")
    shipping_profile = ShippingProfile("medium", "foam-packed insured ground parcel", "Test all functions, disclose hygiene-related limitations, and fully drain equipment before shipping.")
    typical_margins = MarginRange(0.20, 0.50)
    pricing_providers = ("eBay sold listings", "Facebook Marketplace", "Amazon sold offers")
    common_model_prefixes = ("Barista", "DC", "J", "V")
    related_categories = ("home-garden", "electronics", "power-tools")
