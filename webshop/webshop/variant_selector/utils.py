import frappe
from erpnext.utilities.product import get_price
from frappe.utils import cint, flt

from webshop.webshop.doctype.webshop_settings.webshop_settings import (
    get_shopping_cart_settings,
)
from webshop.webshop.shopping_cart.cart import _set_price_list, get_party
from webshop.webshop.shopping_cart.product_info import get_product_info_for_website
from webshop.webshop.variant_selector.item_variants_cache import (
    ItemVariantsCacheManager,
)

PRIMARY_FILTER_CANDIDATES = (
    {"Rozmiar", "Size"},
    {"Tkanina", "Fabric"},
)


def get_item_codes_by_attributes(attribute_filters, template_item_code=None):
    items = []

    for attribute, values in attribute_filters.items():
        attribute_values = values

        if not isinstance(attribute_values, list):
            attribute_values = [attribute_values]

        if not attribute_values:
            continue

        wheres = []
        query_values = []
        for attribute_value in attribute_values:
            wheres.append("( attribute = %s and attribute_value = %s )")
            query_values += [attribute, attribute_value]

        attribute_query = " or ".join(wheres)

        if template_item_code:
            variant_of_query = "AND t2.variant_of = %s"
            query_values.append(template_item_code)
        else:
            variant_of_query = ""

        query = """
			SELECT
				t1.parent
			FROM
				`tabItem Variant Attribute` t1
			WHERE
				1 = 1
				AND (
					{attribute_query}
				)
				AND EXISTS (
					SELECT
						1
					FROM
						`tabItem` t2
					WHERE
						t2.name = t1.parent
						{variant_of_query}
				)
			GROUP BY
				t1.parent
			ORDER BY
				NULL
		""".format(attribute_query=attribute_query, variant_of_query=variant_of_query)

        item_codes = set(
            [r[0] for r in frappe.db.sql(query, query_values)]
        )  # nosemgrep
        items.append(item_codes)

    res = list(set.intersection(*items))

    return res


@frappe.whitelist(allow_guest=True)
def get_attributes_and_values(item_code):
    """Build a list of attributes and their possible values.
    This will ignore the values upon selection of which there cannot exist one item.
    """
    item_cache = ItemVariantsCacheManager(item_code)
    item_variants_data = item_cache.get_item_variants_data()

    attributes = get_item_attributes(item_code)
    attribute_list = [a.attribute for a in attributes]

    valid_options = {}
    for item_code, attribute, attribute_value in item_variants_data:
        if attribute in attribute_list:
            valid_options.setdefault(attribute, set()).add(attribute_value)

    item_attribute_values = frappe.db.get_all(
        "Item Attribute Value",
        ["parent", "attribute_value", "idx"],
        order_by="parent asc, idx asc",
    )
    ordered_attribute_value_map = frappe._dict()
    for iv in item_attribute_values:
        ordered_attribute_value_map.setdefault(iv.parent, []).append(iv.attribute_value)

    """Numeric attributes are not stored in the Item Attribute Value table.
	However, they are included in valid_options. If they are not found in ordered_attribute_value_map
	sort and add them to it. This does not include the entire range if there is no
	product associated with specific number. Only possible values are returned.
	"""
    for attr_name in attribute_list:
        if attr_name not in ordered_attribute_value_map:
            numeric_list = sorted(
                [i for i in valid_options[attr_name] if i.replace(".", "").isnumeric()],
                key=float,
            )
            ordered_attribute_value_map[attr_name] = numeric_list

    # build attribute values in idx order
    for attr in attributes:
        valid_attribute_values = valid_options.get(attr.attribute, [])
        ordered_values = ordered_attribute_value_map.get(attr.attribute, [])
        attr["values"] = [v for v in ordered_values if v in valid_attribute_values]

    return attributes


@frappe.whitelist(allow_guest=True)
def get_variant_selector_config(item_code):
    attributes = get_attributes_and_values(item_code)
    primary_attributes = get_primary_filter_attributes(attributes)

    return {
        "attributes": attributes,
        "primary_attributes": primary_attributes,
        "secondary_attributes": [
            attr.attribute
            for attr in attributes
            if attr.attribute not in primary_attributes
        ],
    }


@frappe.whitelist(allow_guest=True)
def get_variant_rows(item_code, selected_filters=None):
    selected_filters = frappe.parse_json(selected_filters) if selected_filters else {}

    attributes = get_attributes_and_values(item_code)
    attribute_names = [attr.attribute for attr in attributes]
    primary_attributes = get_primary_filter_attributes(attributes)
    secondary_attributes = [
        attr_name
        for attr_name in attribute_names
        if attr_name not in primary_attributes
    ]

    item_cache = ItemVariantsCacheManager(item_code)
    item_attribute_value_map = item_cache.get_item_attribute_value_map()
    matching_item_codes = set(item_attribute_value_map.keys())

    if selected_filters:
        matching_item_codes = get_items_with_selected_attributes(
            item_code, selected_filters
        )

    # Filter by is_sales_item to exclude variants that are not for sale
    if matching_item_codes:
        sales_items = frappe.db.get_all(
            "Item",
            filters={"name": ["in", list(matching_item_codes)], "is_sales_item": 1},
            pluck="name",
        )
        matching_item_codes = set(sales_items)

    cart_qty_map = get_current_cart_qty_map(matching_item_codes)
    ordered_attribute_values = item_cache.get_ordered_attribute_values()
    rows = []

    for variant_code in matching_item_codes:
        attribute_map = item_attribute_value_map.get(variant_code, {})
        product_info = get_product_info_for_website(
            variant_code, skip_quotation_creation=True
        ).get("product_info", {})
        price_info = product_info.get("price") or {}
        is_stock_item = cint(
            frappe.get_cached_value("Item", variant_code, "is_stock_item")
        )
        can_order = bool(
            product_info.get("on_backorder")
            or not is_stock_item
            or product_info.get("in_stock")
            or cint(get_shopping_cart_settings().allow_items_not_in_stock)
        )

        rows.append(
            {
                "item_code": variant_code,
                "item_name": frappe.get_cached_value("Item", variant_code, "item_name"),
                "attributes": attribute_map,
                "secondary_attributes": {
                    attr_name: attribute_map.get(attr_name, "")
                    for attr_name in secondary_attributes
                },
                "formatted_price": price_info.get("formatted_price_sales_uom", ""),
                "price_number": flt(price_info.get("price_list_rate", 0)),
                "in_stock": cint(product_info.get("in_stock")),
                "on_backorder": cint(product_info.get("on_backorder")),
                "stock_qty": flt(product_info.get("stock_qty")),
                "qty_in_cart": flt(cart_qty_map.get(variant_code, 0)),
                "can_order": can_order,
            }
        )

    rows.sort(
        key=lambda row: get_variant_sort_key(
            row, attribute_names, ordered_attribute_values
        )
    )

    return {
        "primary_attributes": primary_attributes,
        "secondary_attributes": secondary_attributes,
        "rows": rows,
    }


@frappe.whitelist(allow_guest=True)
def get_next_attribute_and_values(item_code, selected_attributes):
    from erpnext.stock.doctype.warehouse.warehouse import get_child_warehouses

    """Find the count of Items that match the selected attributes.
	Also, find the attribute values that are not applicable for further searching.
	If less than equal to 10 items are found, return item_codes of those items.
	If one item is matched exactly, return item_code of that item.
	"""
    selected_attributes = frappe.parse_json(selected_attributes)

    item_cache = ItemVariantsCacheManager(item_code)
    item_variants_data = item_cache.get_item_variants_data()

    attributes = get_item_attributes(item_code)
    attribute_list = [a.attribute for a in attributes]
    filtered_items = get_items_with_selected_attributes(item_code, selected_attributes)

    next_attribute = None

    for attribute in attribute_list:
        if attribute not in selected_attributes:
            next_attribute = attribute
            break

    valid_options_for_attributes = frappe._dict()

    for a in attribute_list:
        valid_options_for_attributes[a] = set()

        selected_attribute = selected_attributes.get(a, None)
        if selected_attribute:
            # already selected attribute values are valid options
            valid_options_for_attributes[a].add(selected_attribute)

    for row in item_variants_data:
        item_code, attribute, attribute_value = row
        if (
            item_code in filtered_items
            and attribute not in selected_attributes
            and attribute in attribute_list
        ):
            valid_options_for_attributes[attribute].add(attribute_value)

    optional_attributes = item_cache.get_optional_attributes()
    exact_match = []
    # search for exact match if all selected attributes are required attributes
    if len(selected_attributes.keys()) >= (
        len(attribute_list) - len(optional_attributes)
    ):
        item_attribute_value_map = item_cache.get_item_attribute_value_map()
        for item_code, attr_dict in item_attribute_value_map.items():
            if item_code in filtered_items and set(attr_dict.keys()) == set(
                selected_attributes.keys()
            ):
                exact_match.append(item_code)

    filtered_items_count = len(filtered_items)

    if exact_match:
        cart_settings = get_shopping_cart_settings()
        product_info = get_item_variant_price_dict(exact_match[0], cart_settings)
        qty_in_cart = get_current_cart_qty_map(exact_match).get(exact_match[0], 0)

        if product_info:
            product_info["is_stock_item"] = frappe.get_cached_value(
                "Item", exact_match[0], "is_stock_item"
            )
            product_info["allow_items_not_in_stock"] = cint(
                cart_settings.allow_items_not_in_stock
            )
            product_info["qty"] = qty_in_cart
    else:
        product_info = None

    product_id = ""
    warehouse = ""
    if exact_match or filtered_items:
        if exact_match and len(exact_match) == 1:
            product_id = exact_match[0]
        elif filtered_items_count == 1:
            product_id = list(filtered_items)[0]

    if product_id:
        warehouse = frappe.get_cached_value(
            "Website Item", {"item_code": product_id}, "website_warehouse"
        )

    available_qty = 0.0
    if warehouse and frappe.get_cached_value("Warehouse", warehouse, "is_group") == 1:
        warehouses = get_child_warehouses(warehouse)
    else:
        warehouses = [warehouse] if warehouse else []

    for warehouse in warehouses:
        available_qty += flt(
            frappe.db.get_value(
                "Bin", {"item_code": product_id, "warehouse": warehouse}, "actual_qty"
            )
        )

    return {
        "next_attribute": next_attribute,
        "valid_options_for_attributes": valid_options_for_attributes,
        "filtered_items_count": filtered_items_count,
        "filtered_items": filtered_items if filtered_items_count < 10 else [],
        "exact_match": exact_match,
        "product_info": product_info,
        "available_qty": available_qty,
    }


def get_items_with_selected_attributes(item_code, selected_attributes):
    item_cache = ItemVariantsCacheManager(item_code)
    attribute_value_item_map = item_cache.get_attribute_value_item_map()

    items = []
    for attribute, values in selected_attributes.items():
        if not isinstance(values, (list, tuple, set)):
            values = [values]
        values = [value for value in values if value not in (None, "")]
        if not values:
            continue

        filtered_items = set()
        for value in values:
            filtered_items.update(attribute_value_item_map.get((attribute, value), []))

        if not filtered_items:
            return set()

        items.append(filtered_items)

    if not items:
        return set(item_cache.get_item_attribute_value_map().keys())

    return set.intersection(*items)


# utilities


def get_item_attributes(item_code):
    attributes = frappe.db.get_all(
        "Item Variant Attribute",
        fields=["attribute"],
        filters={"parenttype": "Item", "parent": item_code},
        order_by="idx asc",
    )

    optional_attributes = ItemVariantsCacheManager(item_code).get_optional_attributes()

    for a in attributes:
        if a.attribute in optional_attributes:
            a.optional = True

    return attributes


def get_item_variant_price_dict(item_code, cart_settings):
    if cart_settings.enabled and cart_settings.show_price:
        is_guest = frappe.session.user == "Guest"
        party = get_party(create=False)
        # Show Price if logged in.
        # If not logged in, check if price is hidden for guest.
        if not is_guest or not cart_settings.hide_price_for_guest:
            price_list = _set_price_list(cart_settings, None)
            price = get_price(
                item_code,
                price_list,
                cart_settings.default_customer_group,
                cart_settings.company,
                party=party,
            )
            return {"price": price}

    return None


def get_primary_filter_attributes(attributes):
    required_attributes = [
        attr.attribute for attr in attributes if not attr.get("optional")
    ]
    primary_attributes = []

    for candidates in PRIMARY_FILTER_CANDIDATES:
        match = next((attr for attr in required_attributes if attr in candidates), None)
        if match and match not in primary_attributes:
            primary_attributes.append(match)

    for attribute in required_attributes:
        if attribute not in primary_attributes:
            primary_attributes.append(attribute)

    return primary_attributes[: min(2, len(primary_attributes))]


def get_current_cart_qty_map(item_codes):
    item_codes = list(item_codes or [])
    if not item_codes:
        return {}

    party = get_party(create=False)
    if not party:
        return {}

    quotation_name = frappe.db.get_value(
        "Quotation",
        {
            "party_name": party.name,
            "contact_email": frappe.session.user,
            "order_type": "Shopping Cart",
            "docstatus": 0,
        },
        "name",
        order_by="modified desc",
    )
    if not quotation_name:
        return {}

    return {
        row.item_code: flt(row.qty)
        for row in frappe.get_all(
            "Quotation Item",
            filters={"parent": quotation_name, "item_code": ["in", item_codes]},
            fields=["item_code", "qty"],
        )
    }


def get_variant_sort_key(row, attribute_names, ordered_attribute_values):
    sort_key = []
    for attribute_name in attribute_names:
        value = row["attributes"].get(attribute_name, "")
        ordered_values = ordered_attribute_values.get(attribute_name, [])
        index = (
            ordered_values.index(value)
            if value in ordered_values
            else len(ordered_values)
        )
        sort_key.append(index)
        sort_key.append(value)

    sort_key.append(row["item_code"])
    return tuple(sort_key)
