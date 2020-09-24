# coding: utf-8
# Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
# Copyright (C) 2013 Julius Network Solutions SARL <contact@julius.fr>
# Copyright (C) 2015 Valentin Chemiere <valentin.chemiere@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api


class ServerAction(models.Model):
    """
    Possibility to specify the SMS Gateway when configure this server action
    """
    _inherit = 'ir.actions.server'

    state = fields.Selection(selection_add=[
        ('sms', 'Send SMS'),
    ])
    sms_template_id = fields.Many2one(
        comodel_name='sms.template', string='SMS Template',
        help='Select the SMS Template configuration to use with this action.')
    sms_force_send = fields.Boolean('Force send SMS', default=False)

    @api.model
    def run_action_sms(self, action, eval_context=None):
        if not action.sms_template_id or not self._context.get('active_ids'):
            return False
        cleaned_ctx = dict(self.env.context)
        for res_id in self._context.get('active_ids'):
            action.sms_template_id.with_context(cleaned_ctx).send_sms(
                res_id,
                force_send=action.sms_force_send
            )
        return False
