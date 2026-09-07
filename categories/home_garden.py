from .base import CategoryKnowledge, MarginRange, ShippingProfile


class HomeGardenCategory(CategoryKnowledge):
    name = slug = "home-garden"
    description = "Small home goods, décor, kitchen equipment, lighting, and durable garden items."
    brands = ("Breville", "Dyson", "Herman Miller", "KitchenAid", "Le Creuset", "Nespresso", "Vitamix", "Weber")
    keywords = ("air purifier", "cast iron", "espresso", "lamp", "mixer", "patio", "vacuum", "vintage")
    common_misspellings = ("kitchen aid", "le cruset", "nespressoo", "vaccuum")
    seasonality = "Gardening and patio equipment peak in spring; kitchen, décor, and appliances lift in Q4 and during moves."
    repair_opportunities = ("cord replacement", "descaling", "filter replacement", "hardware tightening")
    shipping_profile = ShippingProfile("medium", "foam-packed insured parcel or local pickup", "Check for cracks, missing accessories, and electrical safety; favor local pickup for fragile or bulky items.")
    typical_margins = MarginRange(0.20, 0.55)
    pricing_providers = ("eBay sold listings", "Facebook Marketplace", "Chairish")
    common_model_prefixes = ("Artisan", "DC", "Eames", "Ninja")
    related_categories = ("power-tools", "electronics", "appliances")
