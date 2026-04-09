from django.contrib.admin import AdminSite


class BoholanaAdminSite(AdminSite):
    site_header = 'Boholana E-Realty Administration'
    site_title = 'Boholana E-Realty Admin'
    index_title = 'Boholana E-Realty System Administration Panel'
    site_url = '/'