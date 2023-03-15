from odoo import models, Command
from odoo.exceptions import AccessError

class EstateProperty(models.Model):
    _inherit = "estate.property"

    def action_sold(self):
        print("Passei por aqui!!!!!!")
        self._create_invoice()
        return super().action_sold()
    
    def _create_invoice(self):
        if not self.env['account.move'].check_access_rights('create', False):
            try:
                self.check_access_rights('write')
                self.check_access_rule('write')
            except AccessError:
                return self.env['account.move']

        for record in self:    
            self.env['account.move'].create(
                {
                    "partner_id": record.buyer_id.id,
                    "move_type": 'out_invoice',
                    "invoice_line_ids": [
                        Command.create({
                            "name": r"6% selling price",
                            "quantity": 1,
                            "price_unit": record.selling_price * 0.06
                        }),
                        Command.create({
                            "name": "Administrative fees",
                            "quantity": 1,
                            "price_unit": 100.00
                        })
                    ]
                }
            )
