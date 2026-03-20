# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import flt
from webshop.webshop.doctype.item_review.item_review import get_customer
from webshop.webshop.shopping_cart.product_info import get_product_info_for_website
from webshop.webshop.utils.product import get_non_stock_item_status


class ProductQuery:
    """Query engine for product listing

    Attributes:
            fields (list): Fields to fetch in query
            conditions (string): Conditions for query building
            or_conditions (string): Search conditions
            page_length (Int): Length of page for the query
            settings (Document): Webshop Settings DocType
    """

    def __init__(self):
        self.settings = frappe.get_doc("Webshop Settings")
        self.page_length = self.settings.products_per_page or 20

        self.or_filters = []
        self.filters = [["published", "=", 1]]
        self.fields = [
            "web_item_name",
            "name",
            "item_name",
            "item_code",
            "website_image",
            "variant_of",
            "has_variants",
            "item_group",
            "web_long_description",
            "short_description",
            "route",
            "website_warehouse",
            "ranking",
            "on_backorder",
        ]

    def query(
        self, attributes=None, fields=None, search_term=None, start=0, item_group=None
    ):
        """
        Args:
                attributes (dict, optional): Item Attribute filters
                fields (dict, optional): Field level filters
                search_term (str, optional): Search term to lookup
                start (int, optional): Page start

        Returns:
                dict: Dict containing items, item count & discount range
        """
        # track if discounts included in field filters
        self.filter_with_discount = bool(fields.get("discount"))
        result, discount_list, website_item_groups, cart_items, count = (
            [],
            [],
            [],
            [],
            0,
        )

        if fields:
            self.build_fields_filters(fields)
        if item_group:
            self.build_item_group_filters(item_group)
        if search_term:
            self.build_search_filters(search_term)
        if self.settings.hide_variants:
            self.filters.append(["variant_of", "is", "not set"])

        # query results
        if attributes:
            result, count = self.query_items_with_attributes(attributes, start)
        else:
            result, count = self.query_items(start=start)

        # sort combined results by ranking
        result = sorted(result, key=lambda x: x.get("ranking"), reverse=True)

        if self.settings.enabled:
            cart_items = self.get_cart_items()

        result, discount_list = self.add_display_details(
            result, discount_list, cart_items
        )

        discounts = []
        if discount_list:
            discounts = [min(discount_list), max(discount_list)]

        result = self.filter_results_by_discount(fields, result)

        return {"items": result, "items_count": count, "discounts": discounts}

    def query_items(self, start=0):
        """Build a query to fetch Website Items based on field filters."""
        # Use frappe.qb for more complex filtering with joins
        wi = frappe.qb.DocType("Website Item")
        item = frappe.qb.DocType("Item")
        template_item = frappe.qb.DocType("Item").as_("template_item")
        joined_tables = {}

        # Base query with join to Item
        query = (
            frappe.qb.from_(wi)
            .join(item)
            .on(wi.item_code == item.name)
            .left_join(template_item)
            .on((item.variant_of.isnotnull()) & (item.variant_of == template_item.name))
            .select(*[getattr(wi, field) for field in self.fields])
            .distinct()
            .where(
                (wi.published == 1)
                & (item.is_sales_item == 1)
                & ((item.variant_of.isnull()) | (template_item.is_sales_item == 1))
            )
        )

        # Add additional filters
        for filter_item in self.filters:
            parsed_filter = self.parse_filter_item(filter_item)
            if not parsed_filter:
                continue

            doctype_name, field, op, value = parsed_filter
            if (
                doctype_name == "Website Item"
                and field == "published"
                and op == "="
                and value == 1
            ):
                continue  # already added

            query, table = self.get_filter_table(query, joined_tables, wi, item, doctype_name)
            condition = self.build_filter_condition(table, field, op, value)
            if condition is not None:
                query = query.where(condition)

        # Add or_filters if any
        if self.or_filters:
            or_conditions = []
            for or_filter in self.or_filters:
                parsed_filter = self.parse_filter_item(or_filter)
                if not parsed_filter:
                    continue

                doctype_name, field, op, value = parsed_filter
                query, table = self.get_filter_table(
                    query, joined_tables, wi, item, doctype_name
                )
                condition = self.build_filter_condition(table, field, op, value)
                if condition is not None:
                    or_conditions.append(condition)
            if or_conditions:
                query = query.where(frappe.qb.or_(*or_conditions))

        # Get count first
        count = len(query.run(as_dict=True))

        # Add ordering and pagination
        query = query.orderby(wi.ranking, order=frappe.qb.desc)

        # If discounts included, return all rows
        page_length = (
            184467440737095516 if self.filter_with_discount else self.page_length
        )

        items = query.limit(page_length).offset(start).run(as_dict=True)

        return items, count

    def parse_filter_item(self, filter_item):
        if len(filter_item) == 3:
            field, op, value = filter_item
            return "Website Item", field, str(op).lower(), value

        if len(filter_item) == 4:
            doctype_name, field, op, value = filter_item
            return doctype_name, field, str(op).lower(), value

        return None

    def get_filter_table(self, query, joined_tables, wi, item, doctype_name):
        if doctype_name == "Website Item":
            return query, wi

        if doctype_name == "Item":
            return query, item

        if doctype_name in joined_tables:
            return query, joined_tables[doctype_name]

        meta = frappe.get_meta(doctype_name, cached=True)
        if not meta.has_field("parent"):
            return query, None

        table_alias = doctype_name.lower().replace(" ", "_")
        table = frappe.qb.DocType(doctype_name).as_(table_alias)
        join_condition = table.parent == wi.name

        if meta.has_field("parenttype"):
            join_condition = join_condition & (table.parenttype == "Website Item")

        query = query.left_join(table).on(join_condition)
        joined_tables[doctype_name] = table

        return query, table

    def build_filter_condition(self, table, field, op, value):
        if not table or not hasattr(table, field):
            return None

        column = getattr(table, field)

        if op == "=":
            return column == value
        if op == "in":
            values = value if isinstance(value, (list, tuple, set)) else [value]
            return column.isin(values)
        if op == "like":
            return column.like(value)
        if op == "is":
            return column.isnull() if value == "not set" else column.isnotnull()

        return None

    def query_items_with_attributes(self, attributes, start=0):
        """Build a query to fetch Website Items based on field & attribute filters."""
        item_codes = []

        for attribute, values in attributes.items():
            if not isinstance(values, list):
                values = [values]

            # get items that have selected attribute & value
            item_code_list = frappe.db.get_all(
                "Item",
                fields=["item_code"],
                filters=[
                    ["published_in_website", "=", 1],
                    ["is_sales_item", "=", 1],
                    ["Item Variant Attribute", "attribute", "=", attribute],
                    ["Item Variant Attribute", "attribute_value", "in", values],
                ],
            )
            item_codes.append({x.item_code for x in item_code_list})

        if item_codes:
            item_codes = list(set.intersection(*item_codes))
            self.filters.append(["item_code", "in", item_codes])

        items, count = self.query_items(start=start)

        return items, count

    def build_fields_filters(self, filters):
        """Build filters for field values

        Args:
                filters (dict): Filters
        """
        for field, values in filters.items():
            if not values or field == "discount":
                continue

            # handle multiselect fields in filter addition
            meta = frappe.get_meta("Website Item", cached=True)
            df = meta.get_field(field)
            if df.fieldtype == "Table MultiSelect":
                child_doctype = df.options
                child_meta = frappe.get_meta(child_doctype, cached=True)
                fields = child_meta.get("fields")
                if fields:
                    self.filters.append(
                        [child_doctype, fields[0].fieldname, "IN", values]
                    )
            elif isinstance(values, list):
                # If value is a list use `IN` query
                self.filters.append([field, "in", values])
            else:
                # `=` will be faster than `IN` for most cases
                self.filters.append([field, "=", values])

    def build_item_group_filters(self, item_group):
        "Add filters for Item group page and include Website Item Groups."
        from webshop.webshop.doctype.override_doctype.item_group import (
            get_child_groups_for_website,
        )

        item_group_filters = []

        item_group_filters.append(["Website Item", "item_group", "=", item_group])
        # Consider Website Item Groups
        item_group_filters.append(["Website Item Group", "item_group", "=", item_group])

        if frappe.db.get_value("Item Group", item_group, "include_descendants"):
            # include child item group's items as well
            # eg. Group Node A, will show items of child 1 and child 2 as well
            # on it's web page
            include_groups = get_child_groups_for_website(item_group, include_self=True)
            include_groups = [x.name for x in include_groups]

            item_group_filters.append(
                ["Website Item", "item_group", "in", include_groups]
            )

        self.or_filters.extend(item_group_filters)

    def build_search_filters(self, search_term):
        """Query search term in specified fields

        Args:
                search_term (str): Search candidate
        """
        # Default fields to search from
        default_fields = {
            "item_code",
            "item_name",
            "web_long_description",
            "item_group",
        }

        # Get meta search fields
        meta = frappe.get_meta("Website Item")
        meta_fields = set(meta.get_search_fields())

        # Join the meta fields and default fields set
        search_fields = default_fields.union(meta_fields)
        if frappe.db.count("Website Item", cache=True) > 50000:
            search_fields.discard("web_long_description")

        # Build or filters for query
        search = "%{}%".format(search_term)
        for field in search_fields:
            self.or_filters.append([field, "like", search])

    def add_display_details(self, result, discount_list, cart_items):
        """Add price and availability details in result."""
        for item in result:
            product_info = get_product_info_for_website(
                item.item_code, skip_quotation_creation=True
            ).get("product_info")

            if product_info and product_info["price"]:
                # update/mutate item and discount_list objects
                self.get_price_discount_info(item, product_info["price"], discount_list)

            if self.settings.show_stock_availability:
                self.get_stock_availability(item)

            item.in_cart = item.item_code in cart_items

            item.wished = False
            if frappe.db.exists(
                "Wishlist Item",
                {"item_code": item.item_code, "parent": frappe.session.user},
            ):
                item.wished = True

        return result, discount_list

    def get_price_discount_info(self, item, price_object, discount_list):
        """Modify item object and add price details."""
        fields = ["formatted_mrp", "formatted_price", "price_list_rate"]
        for field in fields:
            item[field] = price_object.get(field)

        if price_object.get("discount_percent"):
            item.discount_percent = flt(price_object.discount_percent)
            discount_list.append(price_object.discount_percent)

        if item.formatted_mrp:
            item.discount = price_object.get(
                "formatted_discount_percent"
            ) or price_object.get("formatted_discount_rate")

    def get_stock_availability(self, item):
        """Modify item object and add stock details."""
        from webshop.templates.pages.wishlist import (
            get_stock_availability as get_stock_availability_from_template,
        )

        item.in_stock = False
        warehouse = item.get("website_warehouse")
        is_stock_item = frappe.get_cached_value("Item", item.item_code, "is_stock_item")

        if item.get("on_backorder"):
            return

        if not is_stock_item:
            if warehouse:
                # product bundle case
                item.in_stock = get_non_stock_item_status(
                    item.item_code, "website_warehouse"
                )
            else:
                item.in_stock = True
        elif warehouse:
            # stock item and has warehouse
            item.in_stock = get_stock_availability_from_template(
                item.item_code, warehouse
            )

    def get_cart_items(self):
        customer = get_customer(silent=True)
        if customer:
            quotation = frappe.get_all(
                "Quotation",
                fields=["name"],
                filters={
                    "party_name": customer,
                    "contact_email": frappe.session.user,
                    "order_type": "Shopping Cart",
                    "docstatus": 0,
                },
                order_by="modified desc",
                limit_page_length=1,
            )
            if quotation:
                items = frappe.get_all(
                    "Quotation Item",
                    fields=["item_code"],
                    filters={"parent": quotation[0].get("name")},
                )
                items = [row.item_code for row in items]
                return items

        return []

    def filter_results_by_discount(self, fields, result):
        if fields and fields.get("discount"):
            discount_percent = frappe.utils.flt(fields["discount"][0])
            result = [
                row
                for row in result
                if row.get("discount_percent")
                and row.discount_percent <= discount_percent
            ]

        if self.filter_with_discount:
            # no limit was added to results while querying
            # slice results manually
            result[: self.page_length]

        return result
