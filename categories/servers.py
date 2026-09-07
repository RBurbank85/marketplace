from .base import CategoryKnowledge, MarginRange, ShippingProfile


class ServersCategory(CategoryKnowledge):
    name = slug = "servers"
    description = "Rack servers, storage arrays, and enterprise compute hardware."
    brands = ("Dell", "HPE", "HP", "Lenovo", "Supermicro", "Cisco", "IBM", "Synology", "QNAP")
    keywords = (
        "server",
        "rackmount",
        "blade",
        "poweredge",
        "proliant",
        "xeon",
        "raid",
        "nas",
        "san",
        "hypervisor",
        "storage array",
        "workstation",
    )
    common_misspellings = ("power edge", "proliant", "super micro", "rack mount")
    seasonality = "Steady B2B demand; strongest after enterprise refresh cycles and fiscal year-end liquidations."
    repair_opportunities = (
        "replace failed drives",
        "add RAM",
        "firmware update",
        "fan or power-supply replacement",
    )
    shipping_profile = ShippingProfile(
        "heavy",
        "freight or double-boxed insured ground",
        "Confirm rails, drives, and licensing; pack against rack-ear damage.",
    )
    typical_margins = MarginRange(0.25, 0.55)
    pricing_providers = ("eBay sold listings", "ServerMonkey", "IT Creations")
    common_model_prefixes = ("PowerEdge", "ProLiant", "ThinkSystem", "SuperServer")
    related_categories = ("networking", "industrial", "office-equipment")
