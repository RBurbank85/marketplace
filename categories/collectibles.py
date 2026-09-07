from .base import CategoryKnowledge, MarginRange, ShippingProfile


class CollectiblesCategory(CategoryKnowledge):
    name = slug = "collectibles"
    description = "Trading cards, action figures, toys, comics, die-cast, and pop-culture collectibles."
    brands = ("Bandai", "Hasbro", "LEGO", "Mattel", "Nintendo", "Pokémon", "PSA", "Topps")
    keywords = ("action figure", "blind box", "comic", "graded", "pokemon", "sealed", "trading card", "vintage")
    common_misspellings = ("collectable", "legos", "pokeman", "unopend")
    seasonality = "Holiday gifting is strongest; releases, conventions, anniversaries, and media launches create short demand spikes."
    repair_opportunities = ("bubble protection", "card cleaning review", "completeness check", "loose-joint stabilization")
    shipping_profile = ShippingProfile("small", "rigid mailer or insured box", "Photograph condition closely; never promise grade, authenticity, or unopened contents without evidence.")
    typical_margins = MarginRange(0.25, 0.70)
    pricing_providers = ("eBay sold listings", "130point", "PriceCharting")
    common_model_prefixes = ("PSA", "CGC", "Funko", "Hot Wheels")
    related_categories = ("gaming", "watches", "books-media")
