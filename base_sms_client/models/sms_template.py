# coding: utf-8
# Copyright (C) 2020 David Gómez <david.gomez@factorlibre.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import models, fields, api, _
from odoo.tools import pycompat


class SmsTemplate(models.Model):
    _name = 'sms.template'
    _description = 'SMS Template'

    name = fields.Char('Name', required=True, translate=True)
    model_id = fields.Many2one(
        'ir.model', 'Applies to',
        help="The type of document this template can be used with")
    model = fields.Char(
        'Related Document Model',
        related='model_id.model', index=True, store=True, readonly=True)
    body = fields.Text('Body', translate=True)
    mobile_to = fields.Char(
        'To (Mobile)', help="Comma-separated recipient mobiles.")
    partner_to = fields.Char(
        'To (Partners)',
        help="Comma-separated ids of recipient partners (placeholders may be "
        "used here)")
    gateway_id = fields.Many2one('sms.gateway', 'SMS Gateway')
    lang = fields.Char(
        'Language',
        help="Optional translation language (ISO code) to select when sending "
        "out an email. "
        "If not set, the english version will be used. "
        "This should usually be a placeholder expression "
        "that provides the appropriate language, e.g. "
        "${object.partner_id.lang}.",
        placeholder="${object.partner_id.lang}")

    @api.model
    def render_template(
        self,
        template_txt,
        model,
        res_ids
    ):
        result = self.env['mail.template'].render_template(
            template_txt,
            model,
            res_ids,
            None
        )
        return result

    @api.multi
    def generate_sms(self, res_ids, fields=None):
        self.ensure_one()
        multi_mode = True
        if isinstance(res_ids, pycompat.integer_types):
            res_ids = [res_ids]
            multi_mode = False
        if fields is None:
            fields = [
                'body',
                'mobile_to',
                'partner_to',
            ]

        res_ids_to_templates = self.get_sms_template(res_ids)

        # templates: res_id -> template; template -> res_ids
        templates_to_res_ids = {}
        for res_id, template in res_ids_to_templates.items():
            templates_to_res_ids.setdefault((
                template,
                template.env.context.get('lang')
            ), []).append(res_id)

        results = dict()
        SmsGateway = self.env['sms.gateway']
        for template, template_res_ids in templates_to_res_ids.items():
            template = template[0]
            Template = self.env['sms.template']
            if template.lang:
                Template = Template.with_context(
                    lang=template._context.get('lang')
                )
            for field in fields:
                generated_field_values = Template.render_template(
                    getattr(template, field),
                    template.model,
                    template_res_ids
                )
                for res_id, field_value in generated_field_values.items():
                    # Update mobile_to and partner_to
                    if field in ['mobile_to', 'partner_to']:
                        if not field_value:
                            continue
                        field_value = field_value.split(',')
                    if field == 'partner_to' and field_value:
                        field_value = list(map(
                            lambda p: int(p),
                            field_value
                        ))
                    results.setdefault(res_id, dict())[field] = field_value
            # update values for all res_ids
            for res_id in template_res_ids:
                values = results[res_id]
                # technical settings
                gateway = template.gateway_id
                if not gateway:
                    gateway = SmsGateway.search([
                        ('default_gateway', '=', True)
                    ], limit=1)
                values.update(
                    gateway_id=gateway.id or False,
                    model=template.model,
                    res_id=res_id or False,
                )
        return multi_mode and results or results[res_ids[0]]

    @api.multi
    def get_sms_template(self, res_ids):
        multi_mode = True
        if isinstance(res_ids, pycompat.integer_types):
            res_ids = [res_ids]
            multi_mode = False

        if res_ids is None:
            res_ids = [None]
        results = dict.fromkeys(res_ids, False)

        if not self.ids:
            return results
        self.ensure_one()

        langs = self.render_template(self.lang, self.model, res_ids)
        for res_id, lang in langs.items():
            if lang:
                template = self.with_context(lang=lang)
            else:
                template = self
            results[res_id] = template

        return multi_mode and results or results[res_ids[0]]

    @api.multi
    def send_sms(
        self,
        res_id,
        force_send=False,
        sms_values={}
    ):
        self.ensure_one()
        SMS = self.env['sms.sms']
        smss = self.env['sms.sms']
        ResPartner = self.env['res.partner']

        # create a sms_sms based on values
        values = self.generate_sms(res_id)
        partner_to = values.pop('partner_to', list())
        mobile_to = values.pop('mobile_to', list())
        values.update(sms_values or {})
        sms_values.update({
            'message': values.get('body'),
            'gateway_id': values.get('gateway_id'),
            'model': values.get('model'),
            'res_id': res_id
        })
        for partner_id in partner_to:
            partner = ResPartner.sudo().browse(partner_id)
            vals = sms_values.copy()
            vals.update({
                'partner_id': partner.id,
                'mobile': partner.mobile
            })
            smss |= SMS.create(vals)

        for mobile in mobile_to:
            vals = sms_values.copy()
            vals.update({
                'mobile': mobile
            })
            smss |= SMS.create(vals)

        if force_send:
            smss.send()
        return smss.ids
