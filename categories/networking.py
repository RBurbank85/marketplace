from .base import CategoryKnowledge, MarginRange, ShippingProfile


class NetworkingCategory(CategoryKnowledge):
    name = slug = "networking"
    description = "Switches, routers, firewalls, wireless, and network appliances."
    brands = ("Cisco", "Juniper", "Ubiquiti", "Aruba", "Fortinet", "MikroTik", "Meraki", "Netgear", "TP-Link")
    keywords = (
        "switch",
        "router",
        "firewall",
        "access point",
        "poe",
        "ethernet",
        "sfp",
        "wireless controller",
        "fiber",
        "managed switch",
        "rackmount",
    )
    common_misspellings = ("ubiquity", "fortigate", "ciscoo", "mikrotik")
    seasonality = "Demand follows office moves and school/business refreshes; steady through the year."
    repair_opportunities = (
        "fan replacement",
        "power-supply testing",
        "firmware reset",
        "port testing",
    )
    shipping_profile = ShippingProfile(
        "medium",
        "anti-static padded insured parcel",
        "Verify cloud/licensing release and include console accessories when available.",
    )
    typical_margins = MarginRange(0.25, 0.55)
    pricing_providers = ("eBay sold listings", "NetworkTigers", "Amazon sold offers")
    common_model_prefixes = ("Catalyst", "ISR", "MX", "USW", "EX")
    related_categories = ("servers", "electronics", "office-equipment")
