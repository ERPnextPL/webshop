import frappe
from frappe import _
from frappe.contacts.doctype.address.address import (
    get_address_display,
    get_default_address,
)
from frappe.utils import cint, escape_html

PICKUP_FROM_WAREHOUSE_FIELD = "custom_pickup_from_warehouse"
PICKUP_WAREHOUSE_FIELD = "custom_pickup_warehouse"
WEBSHOP_PICKUP_ENABLED_FIELD = "custom_enable_warehouse_pickup"
WEBSHOP_PICKUP_WAREHOUSE_FIELD = "custom_pickup_warehouse"


def get_pickup_custom_fields():
    return {
        "Quotation": [
            {
                "default": "0",
                "fieldname": PICKUP_FROM_WAREHOUSE_FIELD,
                "fieldtype": "Check",
                "hidden": 1,
                "insert_after": "shipping_rule",
                "label": "Pickup from Warehouse",
            },
            {
                "fieldname": PICKUP_WAREHOUSE_FIELD,
                "fieldtype": "Link",
                "hidden": 1,
                "insert_after": PICKUP_FROM_WAREHOUSE_FIELD,
                "label": "Pickup Warehouse",
                "options": "Warehouse",
            },
        ],
        "Sales Order": [
            {
                "default": "0",
                "fieldname": PICKUP_FROM_WAREHOUSE_FIELD,
                "fieldtype": "Check",
                "hidden": 1,
                "insert_after": "shipping_rule",
                "label": "Pickup from Warehouse",
            },
            {
                "fieldname": PICKUP_WAREHOUSE_FIELD,
                "fieldtype": "Link",
                "hidden": 1,
                "insert_after": PICKUP_FROM_WAREHOUSE_FIELD,
                "label": "Pickup Warehouse",
                "options": "Warehouse",
            },
        ],
        "Webshop Settings": [
            {
                "default": "0",
                "depends_on": "enable_checkout",
                "description": "Show a warehouse pickup option in the webshop checkout.",
                "fieldname": WEBSHOP_PICKUP_ENABLED_FIELD,
                "fieldtype": "Check",
                "insert_after": "allow_checkout_without_payment",
                "label": "Enable Warehouse Pickup",
            },
            {
                "depends_on": WEBSHOP_PICKUP_ENABLED_FIELD,
                "description": "Warehouse name and address shown to customers for pickup orders.",
                "fieldname": WEBSHOP_PICKUP_WAREHOUSE_FIELD,
                "fieldtype": "Link",
                "insert_after": WEBSHOP_PICKUP_ENABLED_FIELD,
                "label": "Pickup Warehouse",
                "mandatory_depends_on": WEBSHOP_PICKUP_ENABLED_FIELD,
                "options": "Warehouse",
            },
        ],
    }


def is_pickup_from_warehouse(doc) -> bool:
    return cint(doc.get(PICKUP_FROM_WAREHOUSE_FIELD)) == 1


def is_warehouse_pickup_configured() -> bool:
    settings = frappe.get_cached_doc("Webshop Settings")
    return cint(settings.get(WEBSHOP_PICKUP_ENABLED_FIELD)) == 1 and bool(
        settings.get(WEBSHOP_PICKUP_WAREHOUSE_FIELD)
    )


def validate_webshop_pickup_settings(doc, method=None):
    if not cint(doc.get(WEBSHOP_PICKUP_ENABLED_FIELD)):
        return

    get_pickup_warehouse_details(doc.get(WEBSHOP_PICKUP_WAREHOUSE_FIELD), required=True)


def get_configured_pickup_warehouse(required=False) -> str | None:
    settings = frappe.get_cached_doc("Webshop Settings")

    if not cint(settings.get(WEBSHOP_PICKUP_ENABLED_FIELD)):
        if required:
            frappe.throw(_("Warehouse pickup is not enabled in Webshop Settings."))
        return None

    warehouse_name = settings.get(WEBSHOP_PICKUP_WAREHOUSE_FIELD)
    if not warehouse_name:
        if required:
            frappe.throw(
                _("Set Pickup Warehouse in Webshop Settings before enabling pickup.")
            )
        return None

    return warehouse_name


def get_pickup_warehouse(doc=None, required=False) -> str | None:
    warehouse_name = doc.get(PICKUP_WAREHOUSE_FIELD) if doc else None
    return warehouse_name or get_configured_pickup_warehouse(required=required)


def get_pickup_warehouse_details(warehouse_name: str | None = None, required=False):
    warehouse_name = warehouse_name or get_configured_pickup_warehouse(
        required=required
    )
    if not warehouse_name:
        return None

    warehouse = frappe.get_cached_doc("Warehouse", warehouse_name)
    if required:
        validate_pickup_warehouse(warehouse)

    address = get_pickup_warehouse_address(warehouse.name, required=required)
    address_lines = get_pickup_address_lines(address)
    address_display = get_address_display(address.name) if address else None
    if required and not address:
        frappe.throw(
            _("Link an Address to Warehouse {0} before enabling pickup.").format(
                frappe.bold(warehouse.name)
            )
        )

    display_name = warehouse.warehouse_name or warehouse.name
    return frappe._dict(
        {
            "warehouse": warehouse.name,
            "address_name": address.name if address else None,
            "display_name": display_name,
            "address": address_display,
            "address_text": ", ".join(address_lines),
            "shipping_address": "<br>".join(
                part for part in [escape_html(display_name), address_display] if part
            ),
        }
    )


def validate_pickup_warehouse(warehouse):
    if cint(warehouse.disabled):
        frappe.throw(
            _("Pickup Warehouse {0} is disabled.").format(frappe.bold(warehouse.name))
        )

    if cint(warehouse.is_group):
        frappe.throw(
            _("Pickup Warehouse {0} must not be a group warehouse.").format(
                frappe.bold(warehouse.name)
            )
        )


def get_pickup_warehouse_address(warehouse_name: str, required=False):
    address_name = get_default_address("Warehouse", warehouse_name)
    if not address_name:
        address_name = frappe.get_all(
            "Address",
            filters=[
                ["Dynamic Link", "link_doctype", "=", "Warehouse"],
                ["Dynamic Link", "link_name", "=", warehouse_name],
                ["disabled", "=", 0],
            ],
            pluck="name",
            order_by="is_primary_address DESC, is_shipping_address DESC, modified DESC",
            limit=1,
        )
        address_name = address_name[0] if address_name else None

    if not address_name:
        if required:
            frappe.throw(
                _("Link an Address to Warehouse {0} before enabling pickup.").format(
                    frappe.bold(warehouse_name)
                )
            )
        return None

    return frappe.get_cached_doc("Address", address_name)


def get_pickup_address_lines(address) -> list[str]:
    if not address:
        return []

    postal_city = " ".join(
        part for part in [address.get("pincode"), address.get("city")] if part
    )
    return [
        line
        for line in [
            address.get("address_line1"),
            address.get("address_line2"),
            postal_city,
            address.get("state"),
            address.get("country"),
        ]
        if line
    ]


def apply_pickup_to_sales_order(source_doc, sales_order) -> bool:
    if not is_pickup_from_warehouse(source_doc):
        return False

    sales_order.set(PICKUP_FROM_WAREHOUSE_FIELD, 1)
    sales_order.set(PICKUP_WAREHOUSE_FIELD, source_doc.get(PICKUP_WAREHOUSE_FIELD))
    return enforce_pickup_from_warehouse(sales_order)


def enforce_pickup_from_warehouse(doc) -> bool:
    if not is_pickup_from_warehouse(doc):
        return False

    warehouse_name = get_pickup_warehouse(doc, required=True)
    pickup_details = get_pickup_warehouse_details(warehouse_name, required=True)
    changed = False

    current_shipping_rule = doc.get("shipping_rule")
    if current_shipping_rule and remove_shipping_rule_taxes(doc, current_shipping_rule):
        changed = True

    if doc.get("shipping_rule"):
        doc.shipping_rule = None
        changed = True

    if doc.get(PICKUP_WAREHOUSE_FIELD) != pickup_details.warehouse:
        doc.set(PICKUP_WAREHOUSE_FIELD, pickup_details.warehouse)
        changed = True

    if (
        doc.doctype == "Sales Order"
        and doc.get("shipping_address_name") != pickup_details.address_name
    ):
        doc.shipping_address_name = pickup_details.address_name
        changed = True

    if doc.get("shipping_address") != pickup_details.shipping_address:
        doc.shipping_address = pickup_details.shipping_address
        changed = True

    return changed


def clear_pickup_from_warehouse(doc) -> bool:
    changed = False
    current_shipping_rule = doc.get("shipping_rule")

    if current_shipping_rule and remove_shipping_rule_taxes(doc, current_shipping_rule):
        changed = True

    if doc.get("shipping_rule"):
        doc.shipping_rule = None
        changed = True

    pickup_details = None
    try:
        pickup_details = get_pickup_warehouse_details(doc.get(PICKUP_WAREHOUSE_FIELD))
    except (frappe.DoesNotExistError, frappe.ValidationError):
        pass

    if (
        pickup_details
        and doc.get("shipping_address") == pickup_details.shipping_address
    ):
        doc.shipping_address = None
        changed = True

    if (
        doc.doctype == "Sales Order"
        and pickup_details
        and doc.get("shipping_address_name") == pickup_details.address_name
    ):
        doc.shipping_address_name = None
        changed = True

    if doc.get(PICKUP_WAREHOUSE_FIELD):
        doc.set(PICKUP_WAREHOUSE_FIELD, None)
        changed = True

    if doc.get(PICKUP_FROM_WAREHOUSE_FIELD):
        doc.set(PICKUP_FROM_WAREHOUSE_FIELD, 0)
        changed = True

    return changed


def remove_shipping_rule_taxes(doc, shipping_rule_name: str | None) -> bool:
    if not shipping_rule_name or not doc.get("taxes"):
        return False

    shipping_rule = frappe.get_cached_doc("Shipping Rule", shipping_rule_name)
    kept_rows = []
    removed = False

    for row in doc.get("taxes"):
        if (
            row.charge_type == "Actual"
            and row.account_head == shipping_rule.account
            and (row.cost_center or None) == (shipping_rule.cost_center or None)
        ):
            removed = True
            continue

        kept_rows.append(row)

    if removed:
        doc.set("taxes", kept_rows)

    return removed
