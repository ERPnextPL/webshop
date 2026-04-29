# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _

from webshop.webshop.doctype.webshop_settings.webshop_settings import show_attachments
from webshop.webshop.shopping_cart.pickup import (
    get_pickup_warehouse_details,
    is_pickup_from_warehouse,
)


def get_customer_facing_status(doc):
    if "zetka_utils" not in frappe.get_installed_apps():
        return None

    from zetka_utils.overrides.sales_order import (
        get_customer_facing_status as _get_status,
    )

    return _get_status(doc)


def get_related_delivery_notes(doc):
    if doc.doctype != "Sales Order":
        return []

    delivery_note_names = frappe.get_all(
        "Delivery Note Item",
        filters={"against_sales_order": doc.name},
        distinct=True,
        pluck="parent",
    )
    if not delivery_note_names:
        return []

    return frappe.get_all(
        "Delivery Note",
        filters={"name": ["in", delivery_note_names], "docstatus": ["<", 2]},
        fields=["name", "creation", "modified", "docstatus"],
        order_by="creation desc",
    )


def get_related_sales_invoices(doc, delivery_note_names=None):
    if doc.doctype != "Sales Order":
        return []

    filters = {"sales_order": doc.name}
    invoice_names = set(
        frappe.get_all(
            "Sales Invoice Item",
            filters=filters,
            distinct=True,
            pluck="parent",
        )
    )

    if delivery_note_names:
        invoice_names.update(
            frappe.get_all(
                "Sales Invoice Item",
                filters={"delivery_note": ["in", delivery_note_names]},
                distinct=True,
                pluck="parent",
            )
        )

    if not invoice_names:
        return []

    return frappe.get_all(
        "Sales Invoice",
        filters={"name": ["in", list(invoice_names)], "docstatus": ["<", 2]},
        fields=["name", "creation", "modified", "docstatus"],
        order_by="creation desc",
    )


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = True
    context.doc = frappe.get_doc(frappe.form_dict.doctype, frappe.form_dict.name)
    if hasattr(context.doc, "set_indicator"):
        context.doc.set_indicator()

    context.customer_facing_status = None
    context.pickup_warehouse_details = None
    if context.doc.doctype == "Sales Order":
        context.customer_facing_status = get_customer_facing_status(context.doc)
        context.related_delivery_notes = get_related_delivery_notes(context.doc)
        context.related_sales_invoices = get_related_sales_invoices(
            context.doc,
            [delivery_note.name for delivery_note in context.related_delivery_notes],
        )
        if is_pickup_from_warehouse(context.doc):
            context.pickup_warehouse_details = get_pickup_warehouse_details(
                context.doc.get("custom_pickup_warehouse")
            )
    else:
        context.related_delivery_notes = []
        context.related_sales_invoices = []

    if show_attachments():
        context.attachments = get_attachments(
            frappe.form_dict.doctype, frappe.form_dict.name
        )

    context.parents = frappe.form_dict.parents
    context.title = frappe.form_dict.name
    context.payment_ref = frappe.db.get_value(
        "Payment Request", {"reference_name": frappe.form_dict.name}, "name"
    )

    webshop_settings = frappe.get_doc("Webshop Settings")
    context.enabled_checkout = webshop_settings.enable_checkout
    context.can_pay_for_order = bool(
        webshop_settings.payment_gateway_account
        and not webshop_settings.allow_checkout_without_payment
    )

    default_print_format = frappe.db.get_value(
        "Property Setter",
        dict(property="default_print_format", doc_type=frappe.form_dict.doctype),
        "value",
    )
    if default_print_format:
        context.print_format = default_print_format
    else:
        context.print_format = "Standard"

    if not frappe.has_website_permission(context.doc):
        frappe.throw(_("Not Permitted"), frappe.PermissionError)

    if context.doc.get("customer"):
        # check for the loyalty program of the customer
        customer_loyalty_program = frappe.db.get_value(
            "Customer", context.doc.customer, "loyalty_program"
        )
        if customer_loyalty_program:
            from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
                get_loyalty_program_details_with_points,
            )

            loyalty_program_details = get_loyalty_program_details_with_points(
                context.doc.customer, customer_loyalty_program
            )
            context.available_loyalty_points = int(
                loyalty_program_details.get("loyalty_points")
            )

    # show Make Purchase Invoice button based on permission
    context.show_make_pi_button = frappe.has_permission("Purchase Invoice", "create")


def get_attachments(dt, dn):
    return frappe.get_all(
        "File",
        fields=["name", "file_name", "file_url", "is_private"],
        filters={"attached_to_name": dn, "attached_to_doctype": dt, "is_private": 0},
    )
