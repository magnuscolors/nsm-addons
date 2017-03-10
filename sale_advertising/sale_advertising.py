# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution	
#    Copyright (C) 2004-2016 Magnus (<http://www.magnus.nl>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import fields, osv, orm
import openerp.addons.decimal_precision as dp
import time
from openerp.tools.translate import _



class sale_order(orm.Model):
    _inherit = "sale.order"


    def _amount_all(self, cr, uid, ids, name, args, context=None):
        if context is None:
            context = {}

        res = {}
        if context.get('verif_setting_change'):
            company_ids = context.get('company_ids', [])
            company_obj = self.pool['res.company'].browse(cr, uid, company_ids, context=context)
            for company in company_obj:
                treshold = company.verify_order_setting
                maxdiscount = company.verify_discount_setting
                company_id = company.id

                cr.execute("""UPDATE sale_order
                            SET ver_tr_exc=True
                            WHERE (amount_untaxed > %s
                            OR max_discount > %s)
                            AND company_id= %s
                            AND state!='done';
                            UPDATE sale_order
                            SET ver_tr_exc=False
                            WHERE amount_untaxed <= %s
                            AND company_id= %s
                            AND max_discount <= %s
                            AND state!='done'
                            """, ( treshold, maxdiscount, company_id,  treshold, company_id, maxdiscount ))

        else:
            cur_obj = self.pool.get('res.currency')
            for order in self.browse(cr, uid, ids, context=context):
                res[order.id] = {
                    'amount_untaxed': 0.0,
                    'amount_tax': 0.0,
                    'amount_total': 0.0,
                    'ver_tr_exc': None,
                }
                val = val1 = 0.0
                cdiscount = []
                cur = order.pricelist_id.currency_id
                for line in order.order_line:
                    cdiscount.append(line.computed_discount)
                    val1 += line.price_subtotal
                    val += self._amount_line_tax(cr, uid, line, context=context)
                if cdiscount:
                    max_cdiscount = max(cdiscount)
                else: max_cdiscount = 0.0
                res[order.id]['amount_tax'] = cur_obj.round(cr, uid, cur, val)
                res[order.id]['amount_untaxed'] = cur_obj.round(cr, uid, cur, val1)
                res[order.id]['amount_total'] = res[order.id]['amount_untaxed'] + res[order.id]['amount_tax']
                if order.company_id.verify_order_setting < res[order.id]['amount_untaxed'] or order.company_id.verify_discount_setting < max_cdiscount:
                    res[order.id]['ver_tr_exc'] = True
                else:
                    res[order.id]['ver_tr_exc'] = False
        return res

    def _amount_line_tax(self, cr, uid, line, context=None):
        val = 0.0
        for c in self.pool.get('account.tax').compute_all(cr, uid, line.tax_id, line.actual_unit_price * (1-(line.discount or 0.0)/100.0), line.product_uom_qty, line.product_id, line.order_id.partner_id)['taxes']:
            val += c.get('amount', 0.0)
        return val

    def _get_order(self, cr, uid, ids, context=None):
        line_obj = self.pool.get('sale.order.line')
        return list(set(line['order_id'] for line in line_obj.read(
            cr, uid, ids, ['order_id'], load='_classic_write', context=context)))

    def _setting_change(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        context['company_ids'] = ids
        context['verif_setting_change'] = True
        res = ids
        return res

    _columns = {
        'published_customer': fields.many2one('res.partner', 'Published Customer'),
        'advertising_agency': fields.many2one('res.partner', 'Advertising Agency'),
        'customer_contact': fields.many2one('res.partner', 'Customer Contact Person'),
        'traffic_employee': fields.many2one('res.users', 'Traffic Employee',),
        'traffic_comments': fields.text('Traffic Comments'),
        'traffic_appr_date': fields.date('Traffic Confirmation Date', select=True, help="Date on which sales order is confirmed bij Traffic."),
        'opportunity_subject': fields.char('Opportunity Subject', size=64,
                              help="Subject of Opportunity from which this Sales Order is derived."),
        'date_from': fields.function(lambda *a, **k: {}, method=True, type='date', string="Date from"),
        'date_to': fields.function(lambda *a, **k: {}, method=True, type='date', string="Date to"),
        'state': fields.selection([
            ('draft', 'Draft Quotation'),
            ('submitted', 'Submitted for Approval'),
            ('approved1', 'Approved by Sales Mgr'),
            ('approved2', 'Approved by Traffic'),
            ('sent', 'Quotation Sent'),
            ('cancel', 'Cancelled'),
            ('waiting_date', 'Waiting Schedule'),
            ('progress', 'Sales Order'),
            ('manual', 'Sale to Invoice'),
            ('invoice_except', 'Invoice Exception'),
            ('done', 'Done'),
        ], 'Status', readonly=True, track_visibility='onchange',
            help="Gives the status of the quotation or sales order. \nThe exception status is automatically set when a "
                 "cancel operation occurs in the processing of a document linked to the sales order. \nThe 'Waiting Schedule' "
                 "status is set when the invoice is confirmed but waiting for the scheduler to run on the order date.",
            select=True),
        'amount_untaxed': fields.function(_amount_all, digits_compute=dp.get_precision('Account'), string='Untaxed Amount',
                                store={'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 10),
                                       'sale.order.line':(_get_order, ['actual_unit_price', 'tax_id', 'discount', 'product_uom_qty'], 10),
                                        },
                                multi='sums', help="The amount without tax.", track_visibility='always'),
        'amount_tax': fields.function(_amount_all, digits_compute=dp.get_precision('Account'), string='Taxes',
                                store={'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 10),
                                       'sale.order.line':(_get_order, ['actual_unit_price', 'tax_id', 'discount', 'product_uom_qty'], 10),
                                        },
                                multi='sums', help="The tax amount."),
        'amount_total': fields.function(_amount_all, digits_compute=dp.get_precision('Account'), string='Total',
                                store={'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 10),
                                       'sale.order.line':(_get_order, ['actual_unit_price', 'tax_id', 'discount', 'product_uom_qty'], 10),
                                        },
                                multi='sums', help="The total amount."),
        'ver_tr_exc': fields.function(_amount_all, type="boolean", string="Verification Treshold",track_visibility='always',
                                store={'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 20),
                                       'sale.order.line':(_get_order, ['actual_unit_price', 'discount', 'product_uom_qty'], 20),
                                       'res.company':(_setting_change, ['verify_order_setting', 'verify_discount_setting'], 10),
                                        },
                                multi='sums'),

    }

    def onchange_published_customer(self, cr, uid, ids, published_customer, context):
        data = {'advertising_agency':published_customer,'partner_id':published_customer, 'partner_invoice_id': False,
                'partner_shipping_id':False, 'partner_order_id':False}
        if published_customer:
            address = self.onchange_partner_id(cr, uid, ids, published_customer, context)
            data.update(address['value'])
        return {'value' : data }

    def onchange_advertising_agency(self, cr, uid, ids, ad_agency, context):
        data = {'partner_id':ad_agency,'partner_invoice_id': False, 'partner_shipping_id':False, 'partner_order_id':False}
        if ad_agency:
            address = self.onchange_partner_id(cr, uid, ids, ad_agency, context)
            data.update(address['value'])
        return {'value' : data}

    def action_submit(self, cr, uid, ids, context=None):
        for o in self.browse(cr, uid, ids):
            if not o.order_line:
                raise osv.except_osv(_('Error!'),_('You cannot submit a quotation/sales order which has no line.'))
        return True

    def action_approve2(self, cr, uid, ids, context=None):
        for o in self.browse(cr, uid, ids):
            self.write(cr, uid, [o.id],
                       {'state': 'approved2', 'traffic_appr_date': fields.date.context_today(self, cr, uid, context=context)})
        return True

    def onchange_partner_id(self, cr, uid, ids, part, lines, context=None):
        res = super(sale_order, self).onchange_partner_id(cr, uid, ids, part, context=context)
        result = {}
        if lines:
            result['warning'] = {'title':_('Warning'),
                                 'message':_('Changing the Customer can have a change in Agency Discount as a result.'
                                             'This change will only show after saving the order!'
                                             'Before saving the order the order lines and the total amounts may therefor'
                                             'show wrong values.')}
            res.update(result)
        res['value']['user_id'] = uid
        return res

    def update_line_discount(self, cr, uid, ids, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        order = self.browse(cr, uid, ids[0], context=context)
        discount = order.partner_id.agency_discount or 0.0
        line_ids = self.pool['sale.order.line'].search(
            cr, uid, [('order_id', 'in', ids)], context=context)
        if line_ids:
            self.pool['sale.order.line'].write(
                cr, uid, line_ids, {'discount': discount},
                context=context)
        return True

    def write(self, cr, uid, ids, vals, context=None):
        res = super(sale_order, self).write(
            cr, uid, ids, vals, context=context)
        if 'partner_id' in vals:
            self.update_line_discount(cr, uid, ids, context=context)
        return res

    def create(self, cr, uid, vals, context=None):
        res = super(sale_order, self).create(
            cr, uid, vals, context=context)
        self.update_line_discount(cr, uid, [res], context=context)
        return res



class sale_advertising_issue(orm.Model):
    _name = "sale.advertising.issue"
    _inherits = {
        'account.analytic.account': 'analytic_account_id',
    }
    _description="Sale Advertising Issue"


    _columns = {
        'name': fields.char('Name', size=64, required=True),
        'child_ids': fields.one2many('sale.advertising.issue', 'parent_id', 'Issues', domain=[('active', '=', True)]),
        'parent_id': fields.many2one('sale.advertising.issue', 'Title', select=True),
        'analytic_account_id': fields.many2one('account.analytic.account', required=True,
                                      string='Related Analytic Account', ondelete='restrict',
                                      help='Analytic-related data of the issue'),
        'issue_date': fields.related('analytic_account_id','date_publish', type='date', string='Issue Date',),
        'medium': fields.many2one('product.category','Medium', required=True),
        'state': fields.selection([('open','Open'),('close','Close')], 'State'),
        'default_note': fields.text('Default Note'),
    }

    # voor nsm_modules 7.0, date_publish bestaat alleen in nsm.

    _defaults = {
        'state': 'open',
    }




class sale_order_line(orm.Model):
    _inherit = "sale.order.line"

    def _amount_line(self, cr, uid, ids, field_name, arg, context=None):
        tax_obj = self.pool.get('account.tax')
        cur_obj = self.pool.get('res.currency')
        res = {}

        if context is None:
            context = {}
        for line in self.browse(cr, uid, ids, context=context):
            comp_discount = 0.0
            res[line.id] = {
                'price_unit': 0.0,
                'computed_discount': 0.0,
                'price_subtotal': 0.0,
            }
            if not line.order_id.date_order:
                date_order = time.strftime(DEFAULT_SERVER_DATE_FORMAT)
            else: date_order = line.order_id.date_order
            pricelist = line.order_id.pricelist_id and line.order_id.pricelist_id.id or False
            product_id = line.product_id and line.product_id.id or False
            order_partner_id = line.order_id.partner_id and line.order_id.partner_id.id or False
            discount = line.discount or 0.0
            product_uom = line.product_uom and line.product_uom.id or False
            if product_id:
                unit_price = self.pool.get('product.pricelist').price_get(cr, uid, [pricelist], product_id,
                                                        line.product_uom_qty or 1.0, order_partner_id,
                                                    {'uom': product_uom, 'date': date_order,})[pricelist]
            else: unit_price = 0.0
            if unit_price > 0.0:
                comp_discount = (unit_price - line.actual_unit_price)/unit_price * 100.0
            price = line.actual_unit_price * (1 - discount / 100.0)
            taxes = tax_obj.compute_all(cr, uid, line.tax_id, price, line.product_uom_qty, line.product_id, order_partner_id)
            cur = line.order_id.pricelist_id.currency_id
            res[line.id]['price_unit'] = unit_price
            res[line.id]['computed_discount'] = comp_discount
            res[line.id]['price_subtotal'] = cur_obj.round(cr, uid, cur, taxes['total'])
        return res


    _columns = {
        'layout_remark': fields.text('Layout Remark'),
        'title': fields.many2one('sale.advertising.issue', 'Title', domain=[('child_ids','=', True)]),
        'adv_issue_ids': fields.many2many('sale.advertising.issue','sale_order_line_adv_issue_rel', 'order_line_id',
                                          'adv_issue_id',  'Advertising Issues'),
        'adv_issue': fields.many2one('sale.advertising.issue','Advertising Issue'),
        'medium': fields.related('adv_issue', 'medium', type='many2one', relation='product.category',string='Medium', ),
        'ad_class': fields.many2one('product.category', 'Advertising Class'),
        'page_reference': fields.char('Reference of the Page', size=32),
        'ad_number': fields.char('Advertising Reference', size=32),
        'from_date': fields.datetime('Start of Validity'),
        'to_date': fields.datetime('End of Validity'),
        'order_partner_id': fields.related('order_id', 'partner_id', type='many2one', relation='res.partner', string='Customer'),
        'discount_dummy': fields.related('discount', type='float', string='Agency Discount (%)',readonly=True ),
        'actual_unit_price' :fields.float('Actual Unit Price', required=True, digits_compute= dp.get_precision('Product Price'), readonly=True, states={'draft': [('readonly', False)]}),
        'price_unit': fields.function(_amount_line, string='Unit Price', type='float', digits_compute=dp.get_precision('Product Price'), multi=True),
        'computed_discount' :fields.function(_amount_line, string='Computed Discount (%)', digits_compute=dp.get_precision('Account'), type="float", multi=True),
        'price_subtotal': fields.function(_amount_line, string='Subtotal', digits_compute=dp.get_precision('Account'), type="float", multi=True),
    }

    _defaults = {
        'actual_unit_price': 0.0,
        'computed_discount': 0.0,
    }

    def onchange_adv_issue(self, cr, uid, ids, adv_issue=False, adv_issue_ids=False, context=None):
        if context is None:
            context = {}
        data = {}
        vals = {}
        if adv_issue:
            ad_issue = self.pool.get('sale.advertising.issue').browse(cr, uid, adv_issue, context)
            ac = ad_issue.medium and ad_issue.medium.id or False
            data = {'ad_class':[('id', 'child_of', ac), ('type','!=','view')]}
            if adv_issue_ids:
                vals['product_uom_qty'] = len(adv_issue_ids and adv_issue_ids[0][2])
            return {'value': vals, 'domain' : data}
        return

    def onchange_ad_class(self, cr, uid, ids, ad_class=False, context=None):
        if context is None:
            context = {}
        if ad_class:
            data = {}
            template_ids = self.pool.get('product.template').search(cr, uid, [('categ_id', '=', ad_class)], context=context )
            product_ids = self.pool.get('product.product').search(cr, uid, [('product_tmpl_id', 'in', template_ids)], context=context )
            if product_ids :
                data['product_id'] = [('id', 'in', product_ids)]
                return {'domain' : data}
        return

    def onchange_actualup(self, cr, uid, ids, actual_unit_price=False, price_unit=False, qty=0, discount=False, price_subtotal=0.0, context=None):
        result = {}
        if actual_unit_price:
            if price_unit and price_unit > 0.0:
                cdisc = (float(price_unit) - float(actual_unit_price)) / float(price_unit) * 100.0
                result['computed_discount'] = cdisc
                result['price_subtotal'] = actual_unit_price * qty * (1 - discount/100.0)
            else:
                result['computed_discount'] = 0.0
                result['price_subtotal'] = actual_unit_price * qty * (1 - discount / 100.0)
        else:
            result['computed_discount'] = 0.0
            result['price_subtotal'] = price_subtotal
        return {'value': result}

    def product_id_change(self, cr, uid, ids, pricelist, product, qty=0,
            uom=False, qty_uos=0, uos=False, name='', partner_id=False, actual_unit_price=False,
            lang=False, update_tax=True, date_order=False, packaging=False, discount=0.0, fiscal_position=False, flag=False, context=None):
        res = super(sale_order_line, self).product_id_change(cr, uid, ids, pricelist, product, qty=qty,
                                                uom=uom, qty_uos=qty_uos, uos=uos, name=name, partner_id=partner_id,
                                                lang=lang, update_tax=update_tax, date_order=date_order, packaging=packaging,
                                                fiscal_position=fiscal_position, flag=flag, context=context)

        partner = self.pool['res.partner'].browse(cr, uid, partner_id, context=context)
        if partner.is_ad_agency:
            discount = partner.agency_discount
        res['value'].update({'discount': discount, 'discount_dummy': discount})
        if 'price_unit' in res['value']:
            pu = res['value']['price_unit']
        else: pu = 0.0
        res2 = self.onchange_actualup(cr, uid, ids, actual_unit_price=actual_unit_price,
                                        price_unit=pu, qty=qty, discount=discount,
                                        price_subtotal=0.0, context=None)
        res['value'].update(res2['value'])
        return res

    def create_multi_lines(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        import pdb; pdb.set_trace()
        [ol] = self.browse(cr, uid, ids, context=context)
        lines = [x.id for x in ol.order_id.order_line]
        number_ids = len(ol.adv_issue_ids)
        uom_qty = ol.product_uom_qty / number_ids
        uos_qty = ol.product_uos_qty / number_ids
        for ad_iss in ol.adv_issue_ids:
            res = {'adv_issue': ad_iss.id, 'adv_issue_ids': False, 'product_uom_qty': uom_qty, 'product_uos_qty': uos_qty,'title': False}
            vals = self.copy_data(cr, uid, ol.id, default=res, context=context)
            mol_id = self.create(cr, uid, vals, context=context)
            lines.append(mol_id)
        lines.remove(ol.id)
        self.pool['sale.order'].write(cr, uid, [ol.order_id], {'order_line': lines})
        return True

class sale_advertising_proof(orm.Model):
    _name = "sale.advertising.proof"
    _description="Sale Advertising Proof"
    _columns = {
        'name': fields.char('Name', size=32, required=True),
        'address_id':fields.many2one('res.partner','Delivery Address', required=True),
        'number': fields.integer('Number of Copies', required=True),
        'target_id': fields.many2one('sale.order','Target', required=True),
    }
    _defaults = {
        'number': 1,
    }

class crm_make_sale(osv.osv_memory):
    """ Make sale  order for crm """
    _inherit = "crm.make.sale"

    def makeOrder(self, cr, uid, ids, context=None):
        """
        This function  create Quotation on given case.
        @param self: The object pointer
        @param cr: the current row, from the database cursor,
        @param uid: the current user’s ID for security checks,
        @param ids: List of crm make sales' ids
        @param context: A standard dictionary for contextual values
        @return: Dictionary value of created sales order.

        Override from sale_crm.crm_make_sale, in which user_id is not
        taken from partner, but just uid.
        """
        if context is None:
            context = {}
        # update context: if come from phonecall, default state values can make the quote crash lp:1017353
        context.pop('default_state', False)

        case_obj = self.pool.get('crm.lead')
        sale_obj = self.pool.get('sale.order')
        partner_obj = self.pool.get('res.partner')
        data = context and context.get('active_ids', []) or []

        for make in self.browse(cr, uid, ids, context=context):
            partner = make.partner_id
            partner_addr = partner_obj.address_get(cr, uid, [partner.id],
                                                   ['default', 'invoice', 'delivery', 'contact'])
            pricelist = partner.property_product_pricelist.id
            fpos = partner.property_account_position and partner.property_account_position.id or False
            payment_term = partner.property_payment_term and partner.property_payment_term.id or False
            new_ids = []
            for case in case_obj.browse(cr, uid, data, context=context):
                if not partner and case.partner_id:
                    partner = case.partner_id
                    fpos = partner.property_account_position and partner.property_account_position.id or False
                    payment_term = partner.property_payment_term and partner.property_payment_term.id or False
                    partner_addr = partner_obj.address_get(cr, uid, [partner.id],
                                                           ['default', 'invoice', 'delivery', 'contact'])
                    pricelist = partner.property_product_pricelist.id
                if False in partner_addr.values():
                    raise osv.except_osv(_('Insufficient Data!'), _('No address(es) defined for this customer.'))

                vals = {
                    'origin': _('Opportunity: %s') % str(case.id),
                    'section_id': case.section_id and case.section_id.id or False,
                    'categ_ids': [(6, 0, [categ_id.id for categ_id in case.categ_ids])],
                    'shop_id': make.shop_id.id,
                    'partner_id': partner.id,
                    'pricelist_id': pricelist,
                    'partner_invoice_id': partner_addr['invoice'],
                    'partner_shipping_id': partner_addr['delivery'],
                    'date_order': fields.date.context_today(self, cr, uid, context=context),
                    'fiscal_position': fpos,
                    'payment_term': payment_term,
                    'user_id': uid,
                    'opportunity_subject': case.name,
                }
                new_id = sale_obj.create(cr, uid, vals, context=context)
                sale_order = sale_obj.browse(cr, uid, new_id, context=context)
                case_obj.write(cr, uid, [case.id], {'ref': 'sale.order,%s' % new_id})
                new_ids.append(new_id)
                message = _("Opportunity has been <b>converted</b> to the quotation <em>%s</em>.") % (sale_order.name)
                case.message_post(body=message)
            if make.close:
                case_obj.case_close(cr, uid, data)
            if not new_ids:
                return {'type': 'ir.actions.act_window_close'}
            if len(new_ids) <= 1:
                value = {
                    'domain': str([('id', 'in', new_ids)]),
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'sale.order',
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                    'name': _('Quotation'),
                    'res_id': new_ids and new_ids[0]
                }
            else:
                value = {
                    'domain': str([('id', 'in', new_ids)]),
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'res_model': 'sale.order',
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                    'name': _('Quotation'),
                    'res_id': new_ids
                }
            return value




# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

