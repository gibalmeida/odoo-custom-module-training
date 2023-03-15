from odoo import api, fields, models
from dateutil.relativedelta import relativedelta
from datetime import datetime
from odoo.exceptions import UserError, ValidationError


class EstateProperty(models.Model):
    _name = "estate.property"
    _description = "Estate Property"
    _sql_constraints = [
        ('check_expected_price', 'CHECK(expected_price > 0)',
         'The expected price needs to be a positive value.'),
        ('check_selling_price', 'CHECK(selling_price > 0)',
         'The selling prices need to be a positive value.'),
        ('unique_name', 'UNIQUE(name)',
         'This name already has been take for another property.')
    ]
    _order = "id desc"

    name = fields.Char('Title', required=True)
    description = fields.Text('Description')
    postcode = fields.Char()
    date_availability = fields.Date(
        string='Available From', copy=False, default=lambda self: fields.Datetime.today() + relativedelta(months=3))
    expected_price = fields.Float(required=True)
    selling_price = fields.Float(readonly=True, copy=False)
    bedrooms = fields.Integer(default=2)
    living_area = fields.Integer(string='Living Area (sqm)')
    facades = fields.Integer()
    garage = fields.Boolean()
    garden = fields.Boolean()
    garden_area = fields.Float(string='Garden Area (sqm)')
    garden_orientation = fields.Selection(
        string='Garden Orientation',
        selection=[('N', 'North'), ('S', 'South'),
                   ('E', 'East'), ('W', 'West')]
    )
    active = fields.Boolean('Active', default=True)
    state = fields.Selection(
        string='Status',
        selection=[
            ('new', 'New'),
            ('offer_received', 'Offer Received'),
            ('offer_accepted', 'Offer Accepted'),
            ('sold', 'Sold'),
            ('canceled', 'Canceled')
        ],
        default='new'
    )

    property_type_id = fields.Many2one(
        "estate.property.type", string="Property Type")
    salesperson_id = fields.Many2one(
        "res.users", string="Salesperson", index=True, default=lambda self: self.env.user)
    buyer_id = fields.Many2one("res.partner", string="Buyer", copy=False)
    tag_ids = fields.Many2many("estate.property.tag", string="Tags")
    offer_ids = fields.One2many(
        "estate.property.offer", "property_id", string="Offers")

    # Campos computados
    total_area = fields.Float(compute="_compute_total_area")
    best_offer = fields.Float(compute="_compute_best_offer", default=0)

    @api.depends("living_area", "garden_area")
    def _compute_total_area(self):
        for record in self:
            record.total_area = record.living_area + record.garden_area

    @api.depends("offer_ids.price")
    def _compute_best_offer(self):
        for record in self:
            record.best_offer = 0.0
            for offer in record.offer_ids:
                if offer.price > record.best_offer:
                    record.best_offer = offer.price

    @api.constrains('selling_price')
    def _check_offer_price(self):
        for record in self:
            rate = record.selling_price / record.expected_price
            print(rate)
            if rate < 0.90:
                raise ValidationError(r"The selling price needs to be at least 90% of expected price!")

    def action_sold(self):
        for record in self:
            if record.state == 'canceled':
                raise UserError("Cancelled properties cannot be sold!")
            record.state = 'sold'
        return True

    def action_cancel(self):
        for record in self:
            if record.state == 'sold':
                raise UserError("Sold properties cannot be canceled!")
            record.state = 'canceled'
        return True

        

    @api.onchange("garden")
    def _onchange_garden(self):
        if self.garden:
            self.garden_area = 10
            self.garden_orientation = 'N'
        else:
            self.garden_area = 0
            self.garden_orientation = ''

    @api.ondelete(at_uninstall=False)
    def _unlink_except_not_new_or_cancelled(self):
        for record in self:
            if record.state != 'new' and record.state != 'canceled':
                raise UserError('Only new or canceled properties can be deleted!')

class EstatePropertyType(models.Model):
    _name = "estate.property.type"
    _description = "Estate Property Type"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer('Sequence', default=1, help="Used to order properties. Lower is better.")

    property_ids = fields.One2many("estate.property","property_type_id")
    offer_ids = fields.One2many("estate.property.offer","property_type_id")
    offer_count = fields.Integer(compute="_compute_offer_count", default=0)

    @api.depends("offer_ids")
    def _compute_offer_count(self):
        for record in self:
            record.offer_count = len(record.offer_ids)

class EstatePropertyTag(models.Model):
    _name = "estate.property.tag"
    _description = "Estate Property Tag"
    _sql_constraints = [('unique_name','UNIQUE(name)','This tag name has been already taken by another tag!')]
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer()
    
class EstatePropertyOffer(models.Model):
    _name = "estate.property.offer"
    _description = "Estate Property Offer"
    _sql_constraints = [('check_price','CHECK(price > 0)', 'The offer price needs to be a positive value.')]
    _order = "price desc"

    price = fields.Float()
    status = fields.Selection(
        selection=[
            ('accepted', 'Accepted'),
            ('refused', 'Refused')
        ]
    )
    partner_id = fields.Many2one("res.partner", required=True)
    property_id = fields.Many2one("estate.property", required=True)

    validity = fields.Integer(default=7)
    date_deadline = fields.Date(
        compute="_compute_deadline", inverse="_inverse_deadline")
    
    property_type_id = fields.Many2one(related="property_id.property_type_id",store=True)
    
    @api.depends("create_date", "validity")
    def _compute_deadline(self):
        for record in self:
            if isinstance(record.create_date, datetime):
                record.date_deadline = record.create_date + \
                    relativedelta(days=record.validity)
            else:
                record.date_deadline = datetime.now() + relativedelta(days=record.validity)

    def _inverse_deadline(self):
        for record in self:
            difference = record.date_deadline - record.create_date.date()
            record.validity = difference.days

    @api.model
    def create(self, vals):
        record = self.env['estate.property'].browse(vals['property_id'])
        if vals['price'] <= record.best_offer:
            raise UserError("This offer is less than or equal the best offer: %s" % record.best_offer)
        
        record.state = 'offer_received'
        return super().create(vals)

    def action_confirm(self):
        for record in self:
            record.status = 'accepted'
            record.property_id.selling_price = record.price
            record.property_id.buyer_id = record.partner_id
            record.property_id.state = 'offer_accepted'
            for record_offer in record.property_id.offer_ids:
                if record_offer.id != record.id:
                    record_offer.status = 'refused'

    def action_refuse(self):
        for record in self:
            record.status = 'refused'
