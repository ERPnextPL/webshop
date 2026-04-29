import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from webshop.webshop.shopping_cart.pickup import get_pickup_custom_fields


def execute():
    if not frappe.db.exists("DocType", "Webshop Settings"):
        return

    create_custom_fields(get_pickup_custom_fields())
