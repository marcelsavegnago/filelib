# -*- coding: utf-8 -*-

from odoo import models, fields, api
import datetime
import pytz
import logging
from odoo.exceptions import UserError
from odoo.tools.translate import _

from email.utils import formataddr

ADDRESS_FIELDS = ('street', 'street2', 'zip', 'city', 'state_id', 'country_id')

logger = logging.getLogger(__name__)


@api.model
def _lang_get(self):
    return self.env['res.lang'].get_installed()


# put POSIX 'Etc/*' entries at the end to avoid confusing users - see bug 1086728
_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]


def _tz_get(self):
    return _tzs


class e2yun_supplier_info(models.Model):
    _name = 'e2yun.supplier.info'

    def _default_category(self):
        return self.env['res.partner.category'].browse(self._context.get('category_id'))

    def _default_company(self):
        return self.env['res.company']._company_default_get('res.partner')

    name = fields.Char(index=True)
    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)
    date = fields.Date(index=True)
    title = fields.Many2one('res.partner.title')
    parent_id = fields.Many2one('e2yun.supplier.info', string='Related Company', index=True)
    parent_name = fields.Char(related='parent_id.name', readonly=True, string='Parent name')
    child_ids = fields.One2many('e2yun.supplier.info', 'parent_id', string='Contacts', domain=[
        ('active', '=', True)])  # force "active_test" domain to bypass _search() override
    ref = fields.Char(string='Internal Reference', index=True)
    lang = fields.Selection(_lang_get, string='Language', default=lambda self: self.env.lang,
                            help="All the emails and documents sent to this contact will be translated in this language.")
    tz = fields.Selection(_tz_get, string='Timezone', default=lambda self: self._context.get('tz'),
                          help="The partner's timezone, used to output proper date and time values "
                               "inside printed reports. It is important to set a value for this field. "
                               "You should use the same timezone that is otherwise used to pick and "
                               "render date and time values: your computer's timezone.")
    tz_offset = fields.Char(compute='_compute_tz_offset', string='Timezone offset', invisible=True)
    user_id = fields.Many2one('res.users', string='Salesperson',
                              help='The internal user in charge of this contact.')
    vat = fields.Char(string='Tax ID',
                      help="The Tax Identification Number. Complete it if the contact is subjected to government taxes. Used in some legal statements.")
    bank_ids = fields.One2many('res.partner.bank', 'partner_id', string='Banks')
    website = fields.Char()
    comment = fields.Text(string='Notes')

    category_id = fields.Many2many('res.partner.category', column1='partner_id',
                                   column2='category_id', string='Tags', default=_default_category)
    credit_limit = fields.Float(string='Credit Limit')
    barcode = fields.Char(oldname='ean13', help="Use a barcode to identify this contact from the Point of Sale.")
    active = fields.Boolean(default=True)
    customer = fields.Boolean(string='Is a Customer', default= True,
                              help="Check this box if this contact is a customer. It can be selected in sales orders.")
    supplier = fields.Boolean(string='Is a Vendor',
                              help="Check this box if this contact is a vendor. It can be selected in purchase orders.")
    employee = fields.Boolean(help="Check this box if this contact is an Employee.")
    function = fields.Char(string='Job Position')
    type = fields.Selection(
        [('contact', 'Contact'),
         ('invoice', 'Invoice address'),
         ('delivery', 'Shipping address'),
         ('other', 'Other address'),
         ("private", "Private Address"),
         ], string='Address Type',
        default='contact',
        help="Used by Sales and Purchase Apps to select the relevant address depending on the context.")
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char(change_default=True)
    city = fields.Char()
    state_id = fields.Many2one("res.country.state", string='State', ondelete='restrict')
    country_id = fields.Many2one('res.country', string='Country', ondelete='restrict')
    email = fields.Char()
    email_formatted = fields.Char(
        'Formatted Email', compute='_compute_email_formatted',
        help='Format email address "Name <email@domain>"')
    phone = fields.Char()
    mobile = fields.Char()
    is_company = fields.Boolean(string='Is a Company', default=False,
                                help="Check if the contact is a company, otherwise it is a person")
    industry_id = fields.Many2one('res.partner.industry', 'Industry')
    # company_type is only an interface field, do not use it in business logic
    company_type = fields.Selection(string='Company Type',
                                    selection=[('person', 'Individual'), ('company', 'Company')],
                                    compute='_compute_company_type', inverse='_write_company_type')
    company_id = fields.Many2one('res.company', 'Company', index=True, default=_default_company)
    color = fields.Integer(string='Color Index', default=0)
    user_ids = fields.One2many('res.users', 'partner_id', string='Users', auto_join=True)
    partner_share = fields.Boolean(
        'Share Partner', compute='_compute_partner_share', store=True,
        help="Either customer (not a user), either shared user. Indicated the current partner is a customer without "
             "access or with a limited access created for sharing data.")
    contact_address = fields.Char(compute='_compute_contact_address', string='Complete Address')

    # technical field used for managing commercial fields
    commercial_partner_id = fields.Many2one('e2yun.supplier.info', compute='_compute_commercial_partner',
                                            string='Commercial Entity', store=True, index=True)
    commercial_company_name = fields.Char('Company Name Entity', compute='_compute_commercial_company_name',
                                          store=True)
    company_name = fields.Char('Company Name')

    # image: all image fields are base64 encoded and PIL-supported
    image = fields.Binary("Image", attachment=True,
                          help="This field holds the image used as avatar for this contact, limited to 1024x1024px", )
    image_medium = fields.Binary("Medium-sized image", attachment=True,
                                 help="Medium-sized image of this contact. It is automatically " \
                                      "resized as a 128x128px image, with aspect ratio preserved. " \
                                      "Use this field in form views or some kanban views.")
    image_small = fields.Binary("Small-sized image", attachment=True,
                                help="Small-sized image of this contact. It is automatically " \
                                     "resized as a 64x64px image, with aspect ratio preserved. " \
                                     "Use this field anywhere a small image is required.")
    # hack to allow using plain browse record in qweb views, and used in ir.qweb.field.contact
    self = fields.Many2one(comodel_name=_name, compute='_compute_get_ids')

    partner_id = fields.Many2one('res.partner', company_dependent=True, string='Normal Customer')

    property_payment_term_id = fields.Many2one('account.payment.term', company_dependent=True,
                                               string='Customer Payment Terms',
                                               help="This payment term will be used instead of the default one for sales orders and customer invoices",
                                               oldname="property_payment_term")

    # 新增客户中的字段
    customer_id = fields.Char('	Customer Id')
    parent_account = fields.Many2one('res.partner', company_dependent=True, string='母公司')
    activity_user_id = fields.Many2one('res.users', company_dependent=True, string='责任用户')
    secondary_industry_ids = fields.Many2many(
        comodel_name='res.partner.industry', string="Secondary Industries",
        domain="[('id', '!=', industry_id)]")
    is_strategic = fields.Boolean(string='Is Strategic')

    state = fields.Selection([
        ('Draft', '新建'),
        ('done', '完成')
    ], string='Status', readonly=True, required=True, track_visibility='always', copy=False, default='Draft')

    register_no = fields.Char('Registration number')

    organ_code = fields.Char('组织代码')
    business_license = fields.Binary('营业执照',attachment=True)
    annual_turnover = fields.Selection([('1','1000万以下'),('2','1000万-5000万'),('3','5000万-1亿'),('4','1亿-10亿'),('5','10亿-100亿')],'年营业额')
    employees = fields.Selection([('1','500人以下'),('2','500-1000人'),('3','1000-5000人'),('4','5000-10000人')],'企业员工')
    # supply_products = fields.Selection([('1','All'),('2','All / Consumable'),('3','All / Expenses'),
    #                                     ('4','All / Internal'),('5','All / Saleable'),('6','All / Saleable / Office Furniture'),
    #                                     ('7', 'All / Saleable / Services'),('8','All / Saleable / Services / Saleable') , ('9', 'All / Saleable / Software')
    #                                     ],'供应产品类别')
    authenitcation_id = fields.One2many('e2yun.supplier.authentication.info','supplier_info_id','认证信息')
    supplier_user = fields.Integer('Supplier User')

    listed_company = fields.Boolean('是否上市')

    login_name = fields.Char('登录名')
    password = fields.Char('密码')
    confirm_password = fields.Char('确认密码')
    supplier_code = fields.Char('供应商代码')



    _sql_constraints = [
        ('check_name', "CHECK( (type='contact' AND name IS NOT NULL) or (type!='contact') )",
         'Contacts require a name.'),
        ('name_unique', 'unique(name)', "The name you entered already exists"),
        # ('register_no_unique', 'unique(register_no)', "The Duty paragraph you entered already exists"),
    ]

    @api.model
    def create(self, vals):
        vals['supplier_code'] = self.env['ir.sequence'].next_by_code('supplier.code')
        result = super(e2yun_supplier_info, self).create(vals)
        return result

    @api.onchange('name')
    def onchange_name(self):
        name = self.name
        count = self.env['res.partner'].sudo().search_count([('name', '=', name)])
        if count == 0:
            count = self.env['res.partner'].sudo().search_count([('name', '=', name),('active','=',False)])
        if count > 0:
            self.name = False
            msg = _("The name you entered already exists for customers.")
            return {
                'warning': {
                    'title': _('Tips'),
                    'message': msg
                }
            }
        count = self.env['e2yun.supplier.info'].sudo().search_count([('name', '=', name)])
        if count == 0:
            count = self.env['e2yun.supplier.info'].sudo().search_count([('name', '=', name),('active','=',False)])
        if count > 0:
            self.name = False
            msg = _("The name you entered already exists.")
            return {
                'warning': {
                    'title': _('Tips'),
                    'message': msg
                }
            }

    @api.onchange('register_no')
    def onchange_register_no(self):
        register_no = self.register_no
        if register_no:
            count = self.env['res.partner'].sudo().search_count([('register_no', '=', register_no)])
            if count == 0:
                count = self.env['res.partner'].sudo().search_count([('register_no', '=', register_no),('active','=',False)])
            if count > 0:
                self.vat = False
                msg = _("The Duty paragraph you entered already exists for customers.")
                return {
                    'warning': {
                        'title': _('Tips'),
                        'message': msg
                    }
                }

    @api.depends('is_company')
    def _compute_company_type(self):
        for partner in self:
            partner.company_type = 'company' if partner.is_company else 'person'

    @api.depends('is_company', 'parent_id.commercial_partner_id')
    def _compute_commercial_partner(self):
        self.env.cr.execute("""
        WITH RECURSIVE cpid(id, parent_id, commercial_partner_id, final) AS (
            SELECT
                id, parent_id, id,
                (coalesce(is_company, false) OR parent_id IS NULL) as final
            FROM e2yun_supplier_info
            WHERE id = ANY(%s)
        UNION
            SELECT
                cpid.id, p.parent_id, p.id,
                (coalesce(is_company, false) OR p.parent_id IS NULL) as final
            FROM e2yun_supplier_info p
            JOIN cpid ON (cpid.parent_id = p.id)
            WHERE NOT cpid.final
        )
        SELECT cpid.id, cpid.commercial_partner_id
        FROM cpid
        WHERE final AND id = ANY(%s);
        """, [self.ids, self.ids])

        d = dict(self.env.cr.fetchall())
        for partner in self:
            fetched = d.get(partner.id)
            if fetched is not None:
                partner.commercial_partner_id = fetched
            elif partner.is_company or not partner.parent_id:
                partner.commercial_partner_id = partner
            else:
                partner.commercial_partner_id = partner.parent_id.commercial_partner_id

    @api.depends('tz')
    def _compute_tz_offset(self):
        for partner in self:
            partner.tz_offset = datetime.datetime.now(pytz.timezone(partner.tz or 'GMT')).strftime('%z')

    @api.depends('is_company', 'name', 'parent_id.name', 'type', 'company_name')
    def _compute_display_name(self):
        diff = dict(show_address=None, show_address_only=None, show_email=None)
        names = dict(self.with_context(**diff).name_get())
        for partner in self:
            partner.display_name = names.get(partner.id)

    @api.depends(lambda self: self._display_address_depends())
    def _compute_contact_address(self):
        for partner in self:
            partner.contact_address = partner._display_address()

    @api.depends('company_name', 'parent_id.is_company', 'commercial_partner_id.name')
    def _compute_commercial_company_name(self):
        for partner in self:
            p = partner.commercial_partner_id
            partner.commercial_company_name = p.is_company and p.name or partner.company_name

    @api.onchange('company_type')
    def onchange_company_type(self):
        self.is_company = (self.company_type == 'company')

    @api.one
    def _compute_get_ids(self):
        self.self = self.id


    def _display_address_depends(self):
        # field dependencies of method _display_address()
        return self._address_fields() + [
            'country_id.address_format', 'country_id.code', 'country_id.name',
            'company_name', 'state_id.code', 'state_id.name',
        ]

    @api.model
    def _address_fields(self):
        """Returns the list of address fields that are synced from the parent."""
        return list(ADDRESS_FIELDS)

    def _write_company_type(self):
        for partner in self:
            partner.is_company = partner.company_type == 'company'

    @api.depends('name', 'email')
    def _compute_email_formatted(self):
        for partner in self:
            if partner.email:
                partner.email_formatted = formataddr((partner.name or u"False", partner.email or u"False"))
            else:
                partner.email_formatted = ''

    @api.multi
    def _display_address(self, without_company=False):

        '''
        The purpose of this function is to build and return an address formatted accordingly to the
        standards of the country where it belongs.

        :param address: browse record of the res.partner to format
        :returns: the address formatted in a display that fit its country habits (or the default ones
            if not country is specified)
        :rtype: string
        '''
        # get the information that will be injected into the display format
        # get the address format
        address_format = self._get_address_format()
        args = {
            'state_code': self.state_id.code or '',
            'state_name': self.state_id.name or '',
            'country_code': self.country_id.code or '',
            'country_name': self._get_country_name(),
            'company_name': self.commercial_company_name or '',
        }
        for field in self._formatting_address_fields():
            args[field] = getattr(self, field) or ''
        if without_company:
            args['company_name'] = ''
        elif self.commercial_company_name:
            address_format = '%(company_name)s\n' + address_format
        return address_format % args

    @api.model
    def _formatting_address_fields(self):
        """Returns the list of address fields usable to format addresses."""
        return self._address_fields()

    def _display_address_depends(self):
        # field dependencies of method _display_address()
        return self._formatting_address_fields() + [
            'country_id.address_format', 'country_id.code', 'country_id.name',
            'company_name', 'state_id.code', 'state_id.name',
        ]

    @api.model
    def _get_default_address_format(self):
        return "%(street)s\n%(street2)s\n%(city)s %(state_code)s %(zip)s\n%(country_name)s"

    @api.model
    def _get_address_format(self):
        return self.country_id.address_format or self._get_default_address_format()

    @api.multi
    def _get_country_name(self):
        return self.country_id.name or ''

    def customer_transfer_to_normal(self):
        self.ensure_one()
        data = {}
        UNINCLUDE_COL = ['bank_ids', 'user_ids', 'state', 'commercial_partner_id', 'child_ids', 'parent_id',
                         'partner_id', 'display_name', 'tz_offset', 'lang', 'tz', 'self', 'id', 'create_uid',
                         'create_uid', 'create_date', 'write_uid', 'write_date', '__last_update',
                         'message_follower_ids', 'message_partner_ids', 'message_ids', 'website_message_ids',
                         'login_name','password','confirm_password']
        child_datas = []
        many_cols = []
        for field in self.fields_get():
            if self[field] and self[field] != False:
                if field == 'child_ids':
                    # data[field] = []
                    for field2 in self[field]:
                        data1 = {}
                        for field1 in field2.fields_get():
                            if field2[field1] and field2[field1] != False:
                                if field1 in UNINCLUDE_COL:
                                    continue
                                if isinstance(field2[field1], str) or isinstance(field2[field1], int) or isinstance(
                                        field2[field1], float) or isinstance(field2[field1], bool):
                                    data1[field1] = field2[field1]
                                else:
                                    data1[field1] = field2[field1].id
                        child_datas.append(data1)
                    continue
                # if fields.type in ('one2many','many2many'):
                #     values = []
                #     for field2 in self[field]:
                #         values.append(field2.id)
                if field in UNINCLUDE_COL:
                    continue

                if isinstance(self[field], str) or isinstance(self[field], int) or isinstance(self[field],
                                                                                              float) or isinstance(
                    self[field], bool):
                    data[field] = self[field]
                else:
                    if self.fields_get()[field]['type'] in ('one2many', 'many2many'):
                        many_cols.append(field)
                    elif self.fields_get()[field]['type'] == 'binary':
                        data[field] = self[field]
                    else:
                        data[field] = self[field].id
        #data['real_create_uid'] = self.user_id.id
        data['customer'] = False
        data['supplier'] = True
        id = self.env['res.partner'].sudo().create(data)

        if self.login_name:
            user = self.env['res.users'].sudo()
            #supplier_user = self.env['e2yun.supplier.user'].sudo().browse(self.supplier_user)
            groups = []
            #groups.append(self.env.ref('survey.group_survey_user').id)
            groups.append(self.env.ref('base.group_public').id)
            groups.append(self.env.ref('base.group_portal').id)
            user_data = {
                'login' : self.login_name,
                'password' : self.password,
                'name' : self.name,
                'partner_id':id.id,
                'groups_id':[(6, 0, groups)]
            }
            user.create(user_data)
        for many_col in many_cols:
            id[many_col] = self[many_col]
        if child_datas:
            for child_data in child_datas:
                #child_data['real_create_uid'] = self.user_id.id
                child_data['parent_id'] = id.id
                self.env['res.partner'].sudo().create(child_data)
        self.partner_id = id
        # try:
        self.state = 'done'

        if self.company_name:
            company_id = id.create_company()
            if company_id:
                id.parent_id.write({
                'supplier_code':self.supplier_code,
                #'secondary_industry_ids':id.secondary_industry_ids.id,
                'organ_code':self.organ_code,
                'business_license':self.business_license,
                'annual_turnover':self.annual_turnover,
                'employees':self.employees,
                #'authenitcation_id':[id.authenitcation_id],
                'listed_company':self.listed_company,
                'phone':self.phone,
                'mobile':self.mobile,
                'email':self.email,
                'website':self.website,
                })
                id.parent_id.authenitcation_id = id.authenitcation_id
                id.parent_id.secondary_industry_ids = id.secondary_industry_ids


        # except Exception as e:
        #     raise UserError(u'转正式客户失败，请在工作流中添加^完成^状态')
        return False

    # @api.multi
    # def write(self, values):
    #     #读取按钮权限组s
    #     groups_id = self.env.ref('ZCRM.Business_group').id
    #     sql = 'SELECT * from res_groups_users_rel where gid=%s and uid=%s'
    #     self._cr.execute(sql, (groups_id, self._uid,))
    #     groups_users = self._cr.fetchone()
    #
    #     # 草稿状态货有商务组权限可更新数据
    #     if self.state != 'Draft' and not groups_users:
    #         raise UserError('当前状态下无法操作更新，请联系管理员')
    #     return super(e2yun_supplier_info, self).write(values)
