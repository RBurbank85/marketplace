from .base import CategoryKnowledge, MarginRange, ShippingProfile


class FashionCategory(CategoryKnowledge):
    name = slug = "fashion"
    description = "Pre-owned apparel, footwear, handbags, outerwear, and sought-after designer basics."
    brands = ("Arc'teryx", "Carhartt", "Levi's", "Lululemon", "Nike", "Patagonia", "Ralph Lauren", "Zara")
    keywords = ("boots", "denim", "jacket", "leather", "sneakers", "vintage", "workwear", "y2k")
    common_misspellings = ("arcteryx", "lulu lemon", "patagucci", "sneekers")
    seasonality = "Outerwear rises in fall and winter; athleticwear and sandals peak in spring and summer; basics are year-round."
    repair_opportunities = ("button replacement", "de-pilling", "leather conditioning", "minor seam repair")
    shipping_profile = ShippingProfile("small", "clean poly mailer or boxed parcel", "Measure garments, disclose flaws, and authenticate high-risk brands before listing.")
    typical_margins = MarginRange(0.20, 0.60)
    pricing_providers = ("eBay sold listings", "Poshmark sold listings", "The RealReal")
    common_model_prefixes = ("Air Jordan", "501", "Nano Puff", "W")
    related_categories = ("jewelry", "watches", "collectibles")
