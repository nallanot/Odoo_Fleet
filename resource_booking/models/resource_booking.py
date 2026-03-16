from datetime import timedelta
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ResourceBooking(models.Model):
    _name = "resource.booking"
    _description = "Demande de réservation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_datetime desc"

    name = fields.Char(string="Référence", default="New", copy=False)
    resource_id = fields.Many2one("resource.item", required=True, tracking=True)
    requester_id = fields.Many2one(
        "res.users", string="Demandeur", default=lambda self: self.env.user, required=True, tracking=True
    )
    employee_id = fields.Many2one("hr.employee", string="Employé", compute="_compute_employee", store=True)
    manager_user_id = fields.Many2one("res.users", string="Supérieur immédiat", compute="_compute_manager_user", store=True)
    start_datetime = fields.Datetime(string="Début", required=True, tracking=True)
    end_datetime = fields.Datetime(string="Fin", required=True, tracking=True)
    duration_hours = fields.Float(string="Durée (h)", compute="_compute_duration", store=True)
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("to_approve", "En attente d'approbation"),
            ("approved", "Approuvée"),
            ("checked_in", "Check-in effectué"),
            ("done", "Terminée"),
            ("rejected", "Rejetée"),
            ("cancelled", "Annulée"),
        ],
        default="draft",
        tracking=True,
    )
    notes = fields.Text(string="Notes")
    approval_required = fields.Boolean(compute="_compute_approval", store=True)
    approval_actor_id = fields.Many2one("res.users", string="Approbateur", compute="_compute_approval", store=True)
    checkin_token = fields.Char(copy=False)
    checkout_token = fields.Char(copy=False)
    checkin_qr_value = fields.Char(compute="_compute_qr_values")
    checkout_qr_value = fields.Char(compute="_compute_qr_values")

    @api.depends("requester_id")
    def _compute_employee(self):
        for rec in self:
            rec.employee_id = self.env["hr.employee"].search([("user_id", "=", rec.requester_id.id)], limit=1)

    @api.depends("employee_id.parent_id.user_id")
    def _compute_manager_user(self):
        for rec in self:
            rec.manager_user_id = rec.employee_id.parent_id.user_id

    @api.depends("start_datetime", "end_datetime")
    def _compute_duration(self):
        for rec in self:
            rec.duration_hours = 0.0
            if rec.start_datetime and rec.end_datetime:
                rec.duration_hours = (rec.end_datetime - rec.start_datetime).total_seconds() / 3600

    @api.depends("resource_id.approval_policy", "resource_id.manager_id", "manager_user_id")
    def _compute_approval(self):
        for rec in self:
            policy = rec.resource_id.approval_policy
            rec.approval_required = policy != "none"
            if policy == "resource_manager":
                rec.approval_actor_id = rec.resource_id.manager_id
            elif policy == "employee_manager":
                rec.approval_actor_id = rec.manager_user_id
            else:
                rec.approval_actor_id = False

    @api.depends("checkin_token", "checkout_token")
    def _compute_qr_values(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", default="")
        for rec in self:
            rec.checkin_qr_value = f"{base_url}/resource_booking/scan/{rec.checkin_token}" if rec.checkin_token else False
            rec.checkout_qr_value = f"{base_url}/resource_booking/scan/{rec.checkout_token}" if rec.checkout_token else False

    @api.constrains("start_datetime", "end_datetime", "resource_id", "state")
    def _check_booking_constraints(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime and rec.end_datetime <= rec.start_datetime:
                raise ValidationError(_("La date de fin doit être postérieure à la date de début."))
            if rec.state in ["cancelled", "rejected"]:
                continue
            if rec.resource_id and rec.start_datetime and rec.end_datetime:
                domain = [
                    ("id", "!=", rec.id),
                    ("resource_id", "=", rec.resource_id.id),
                    ("state", "in", ["to_approve", "approved", "checked_in", "done", "draft"]),
                    ("start_datetime", "<", rec.end_datetime),
                    ("end_datetime", ">", rec.start_datetime),
                ]
                if self.search_count(domain):
                    raise ValidationError(_("Cette ressource est déjà réservée sur la période sélectionnée."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("resource.booking") or "New"
        records = super().create(vals_list)
        for rec in records:
            rec._ensure_tokens()
        return records

    def _ensure_tokens(self):
        for rec in self:
            if not rec.checkin_token:
                rec.checkin_token = f"in-{secrets.token_urlsafe(16)}"
            if not rec.checkout_token:
                rec.checkout_token = f"out-{secrets.token_urlsafe(16)}"

    def action_submit(self):
        for rec in self:
            rec._ensure_tokens()
            if rec.approval_required and not rec.approval_actor_id:
                raise UserError(_("Aucun approbateur défini. Configurez un gestionnaire de ressource ou un manager employé."))
            rec.state = "to_approve" if rec.approval_required else "approved"
            if rec.approval_required:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=rec.approval_actor_id.id,
                    summary=_("Approbation de réservation"),
                    note=_("Merci de valider la réservation %s.") % rec.name,
                )

    def _check_approver_access(self):
        self.ensure_one()
        if self.env.user.has_group("resource_booking.group_resource_booking_manager"):
            return True
        if self.approval_actor_id == self.env.user:
            return True
        raise AccessError(_("Seul l'approbateur désigné peut effectuer cette action."))

    def action_approve(self):
        for rec in self:
            rec._check_approver_access()
            if rec.state != "to_approve":
                continue
            rec.state = "approved"
            rec.activity_unlink(["mail.mail_activity_data_todo"])

    def action_reject(self):
        for rec in self:
            rec._check_approver_access()
            if rec.state != "to_approve":
                continue
            rec.state = "rejected"
            rec.activity_unlink(["mail.mail_activity_data_todo"])

    def action_checkin(self):
        for rec in self:
            if rec.state != "approved":
                raise UserError(_("Le check-in n'est possible que pour une réservation approuvée."))
            rec.state = "checked_in"

    def action_checkout(self):
        for rec in self:
            if rec.state not in ["checked_in", "approved"]:
                raise UserError(_("Le check-out n'est possible qu'après approbation/check-in."))
            rec.state = "done"

    def action_cancel(self):
        for rec in self:
            rec.state = "cancelled"

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = "draft"

    @api.model
    def action_scan_token(self, token):
        booking = self.search(["|", ("checkin_token", "=", token), ("checkout_token", "=", token)], limit=1)
        if not booking:
            raise UserError(_("QR code invalide ou expiré."))

        if booking.checkin_token == token:
            booking.action_checkin()
            return _("Check-in effectué pour %s") % booking.name

        booking.action_checkout()
        return _("Check-out effectué pour %s") % booking.name

    @api.onchange("start_datetime")
    def _onchange_start_datetime(self):
        if self.start_datetime and not self.end_datetime:
            self.end_datetime = self.start_datetime + timedelta(hours=1)
