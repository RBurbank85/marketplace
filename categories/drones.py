from .base import CategoryKnowledge, MarginRange, ShippingProfile


class DronesCategory(CategoryKnowledge):
    name = slug = "drones"
    description = "Consumer and prosumer drones, controllers, cameras, and compatible accessories."
    brands = ("Autel", "DJI", "Freefly", "GoPro", "Holy Stone", "Parrot", "Skydio", "Yuneec")
    keywords = ("drone", "fpv", "gimbal", "propeller", "remote id", "smart controller", "uav", "video transmitter")
    common_misspellings = ("djii", "dronee", "gimble", "propellor")
    seasonality = "Travel, outdoor recreation, and holiday gifting strengthen demand; commercial accessories move year-round."
    repair_opportunities = ("gimbal calibration", "propeller replacement", "remote pairing", "sensor cleaning")
    shipping_profile = ShippingProfile("small", "insured parcel with battery-compliant handling", "Verify account unbinding, flight readiness, included accessories, and lithium-battery shipping rules.")
    typical_margins = MarginRange(0.20, 0.50)
    pricing_providers = ("eBay sold listings", "MPB", "B&H Used")
    common_model_prefixes = ("Air", "Avata", "Mavic", "Mini")
    related_categories = ("cameras", "electronics", "sporting-goods")
