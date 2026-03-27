# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
import unittest

import frappe

from webshop.webshop.doctype.webshop_settings.webshop_settings import (
	ShoppingCartSetupError,
)
from webshop.webshop.shopping_cart.cart import get_debtors_account


class TestWebshopSettings(unittest.TestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_tax_rule_validation(self):
		frappe.db.sql("update `tabTax Rule` set use_for_shopping_cart = 0")
		frappe.db.commit()  # nosemgrep

		cart_settings = frappe.get_doc("Webshop Settings")
		cart_settings.enabled = 1
		if not frappe.db.get_value("Tax Rule", {"use_for_shopping_cart": 1}, "name"):
			self.assertRaises(ShoppingCartSetupError, cart_settings.validate_tax_rule)

		frappe.db.sql("update `tabTax Rule` set use_for_shopping_cart = 1")

	def test_invalid_filter_fields(self):
		"Check if Item fields are blocked in Webshop Settings filter fields."
		from frappe.custom.doctype.custom_field.custom_field import create_custom_field

		setup_webshop_settings({"enable_field_filters": 1})

		create_custom_field(
			"Item",
			dict(owner="Administrator", fieldname="test_data", label="Test", fieldtype="Data"),
		)
		settings = frappe.get_doc("Webshop Settings")
		settings.append("filter_fields", {"fieldname": "test_data"})

		self.assertRaises(frappe.ValidationError, settings.save)

	def test_checkout_can_remain_enabled_without_payment_gateway(self):
		settings = frappe.get_doc("Webshop Settings")
		original_gateway = settings.payment_gateway_account
		settings.update(
			{
				"enable_checkout": 1,
				"allow_checkout_without_payment": 1,
			}
		)

		settings.save()

		self.assertEqual(settings.enable_checkout, 1)
		self.assertEqual(settings.payment_gateway_account, original_gateway)

	def test_debtors_account_is_not_required_for_checkout_without_payment(self):
		settings = frappe.get_doc("Webshop Settings")
		settings.update(
			{
				"enable_checkout": 1,
				"allow_checkout_without_payment": 1,
			}
		)

		self.assertIsNone(get_debtors_account(settings))

	def test_request_quote_button_can_be_hidden(self):
		settings = frappe.get_doc("Webshop Settings")
		settings.show_request_for_quotation_button = 0
		settings.save()

		self.assertEqual(settings.show_request_for_quotation_button, 0)


def setup_webshop_settings(values_dict):
	"Accepts a dict of values that updates Webshop Settings."
	if not values_dict:
		return

	doc = frappe.get_doc("Webshop Settings", "Webshop Settings")
	doc.update(values_dict)
	doc.save()


test_dependencies = ["Tax Rule"]
