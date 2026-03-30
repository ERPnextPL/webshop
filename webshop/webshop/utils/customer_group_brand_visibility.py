from __future__ import annotations

import frappe

from webshop.webshop.shopping_cart.cart import get_party


def get_customer_for_user(user: str | None = None):
	if not user:
		user = frappe.session.user

	party = get_party(user=user, create=False)
	if party and party.doctype == "Customer":
		return party

	return None


def get_allowed_brand_names_for_user(user: str | None = None) -> list[str]:
	customer = get_customer_for_user(user=user)
	if not customer or not customer.customer_group:
		return []

	allowed_brands = frappe.get_all(
		"Customer Group Brand",
		filters={
			"parenttype": "Customer Group",
			"parentfield": "custom_allowed_brands",
			"parent": customer.customer_group,
		},
		pluck="brand",
	)
	return [brand for brand in allowed_brands if brand]


def get_brand_restriction_for_user(user: str | None = None) -> tuple[bool, list[str]]:
	allowed_brands = get_allowed_brand_names_for_user(user=user)
	return bool(allowed_brands), allowed_brands
