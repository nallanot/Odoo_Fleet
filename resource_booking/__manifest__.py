{
    "name": "Resource Booking",
    "version": "16.0.1.0.0",
    "summary": "Gestion des réservations de ressources avec workflow d'approbation et QR Check-in/Check-out",
    "author": "Codex",
    "category": "Operations",
    "license": "LGPL-3",
    "depends": ["base", "mail", "calendar", "hr", "web"],
    "data": [
        "security/resource_booking_security.xml",
        "security/ir.model.access.csv",
        "data/sequence_data.xml",
        "views/resource_booking_views.xml",
        "views/resource_resource_views.xml"
    ],
    "application": True,
    "installable": True,
}
