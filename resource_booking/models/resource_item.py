from odoo import fields, models


class ResourceItem(models.Model):
    _name = "resource.item"
    _description = "Ressource réservable"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string="Code ressource")
    category = fields.Selection(
        [
            ("equipment", "Équipement"),
            ("vehicle", "Véhicule"),
            ("it", "Informatique"),
            ("other", "Autre"),
        ],
        default="equipment",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(default=True)
    description = fields.Text()
    manager_id = fields.Many2one("res.users", string="Gestionnaire de la ressource")
    approval_policy = fields.Selection(
        [
            ("none", "Aucune approbation"),
            ("resource_manager", "Gestionnaire de la ressource"),
            ("employee_manager", "Supérieur immédiat"),
        ],
        string="Politique d'approbation",
        default="none",
        required=True,
    )
    booking_ids = fields.One2many("resource.booking", "resource_id", string="Réservations")
    color = fields.Integer(string="Couleur Kanban")
