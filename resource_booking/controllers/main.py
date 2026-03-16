from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class ResourceBookingController(http.Controller):
    @http.route("/resource_booking/scan/<string:token>", type="http", auth="user")
    def scan_qr(self, token, **kwargs):
        try:
            message = request.env["resource.booking"].sudo(False).action_scan_token(token)
            body = f"<h2>{message}</h2>"
        except UserError as exc:
            body = f"<h2>{exc}</h2>"
        return request.make_response(body, headers=[("Content-Type", "text/html")])
