from .base import CategoryKnowledge, MarginRange, ShippingProfile


class JewelryCategory(CategoryKnowledge):
    name = slug = "jewelry"
    description = "Fine, vintage, costume, and sterling jewelry with clear material and hallmark signals."
    brands = ("Cartier", "David Yurman", "Kendra Scott", "Pandora", "Tiffany & Co.", "Van Cleef & Arpels", "Vintage", "Zales")
    keywords = ("14k", "925", "bracelet", "earrings", "gold", "necklace", "ring", "sterling")
    common_misspellings = ("braclet", "earings", "sterling silver", "tiffanny")
    seasonality = "Gift occasions and Q4 are strong; bridal and graduation periods support rings and keepsake jewelry."
    repair_opportunities = ("clasp replacement", "gentle cleaning", "prong inspection", "ring sizing referral")
    shipping_profile = ShippingProfile("small", "signature-required insured parcel", "Document weight, hallmarks, measurements, and stones; authenticate luxury pieces and avoid unsupported metal claims.")
    typical_margins = MarginRange(0.20, 0.65)
    pricing_providers = ("eBay sold listings", "WorthPoint", "The RealReal")
    common_model_prefixes = ("925", "14K", "18K", "T&Co")
    related_categories = ("watches", "fashion", "collectibles")
