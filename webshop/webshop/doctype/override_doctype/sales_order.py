from erpnext.selling.doctype.sales_order.sales_order import SalesOrder

from webshop.webshop.shopping_cart.pickup import (
    enforce_pickup_from_warehouse,
    is_pickup_from_warehouse,
)


class WebshopSalesOrder(SalesOrder):
    def before_validate(self):
        if is_pickup_from_warehouse(self):
            enforce_pickup_from_warehouse(self)

        super().before_validate()

    def validate_party_address_and_contact(self):
        if not is_pickup_from_warehouse(self):
            return super().validate_party_address_and_contact()

        party_type, party = self.get_party()

        if not (party_type and party):
            return

        if party_type == "Customer":
            self.validate_party_address(
                party, party_type, self.get("customer_address"), None
            )
        elif party_type == "Supplier":
            self.validate_party_address(party, party_type, self.get("supplier_address"))

        self.validate_party_contact(party, party_type)
