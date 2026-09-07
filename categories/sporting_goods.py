from .base import CategoryKnowledge, MarginRange, ShippingProfile


class SportingGoodsCategory(CategoryKnowledge):
    name = slug = "sporting-goods"
    description = "Fitness, cycling, golf, outdoor, and team-sport equipment and accessories."
    brands = ("Callaway", "Garmin", "Peloton", "Shimano", "Specialized", "TaylorMade", "The North Face", "Yeti")
    keywords = ("bicycle", "camping", "fitness", "golf", "helmet", "kayak", "ski", "treadmill")
    common_misspellings = ("bicycl", "calloway", "pelaton", "tredmill")
    seasonality = "Outdoor, cycling, golf, and fitness demand peak from spring through summer; snow sports peak before and during winter."
    repair_opportunities = ("bearing service", "cable replacement", "grip replacement", "tune-up")
    shipping_profile = ShippingProfile("oversize", "boxed parcel, bike box, or local pickup", "Confirm safety recalls and wear; use local pickup or freight for heavy cardio equipment.")
    typical_margins = MarginRange(0.20, 0.55)
    pricing_providers = ("eBay sold listings", "SidelineSwap", "Pinkbike BuySell")
    common_model_prefixes = ("Edge", "Mavic", "Pro V1", "SRAM")
    related_categories = ("cameras", "home-garden", "power-tools")
