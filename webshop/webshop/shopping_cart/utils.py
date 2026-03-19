# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
import frappe
from frappe import _
from frappe.translate import get_messages_for_app

from webshop.webshop.doctype.webshop_settings.webshop_settings import is_cart_enabled


def show_cart_count():
	if (
		is_cart_enabled()
		and frappe.db.get_value("User", frappe.session.user, "user_type") == "Website User"
	):
		return True

	return False


def set_cart_count(login_manager):
	# since this is run only on hooks login event
	# make sure user is already a customer
	# before trying to set cart count
	user_is_customer = is_customer()
	if not user_is_customer:
		return

	if show_cart_count():
		from webshop.webshop.shopping_cart.cart import set_cart_count

		# set_cart_count will try to fetch existing cart quotation
		# or create one if non existent (and create a customer too)
		# cart count is calculated from this quotation's items
		set_cart_count()


def clear_cart_count(login_manager):
	if show_cart_count():
		frappe.local.cookie_manager.delete_cookie("cart_count")


def update_website_context(context):
	cart_enabled = is_cart_enabled()
	context["shopping_cart_enabled"] = cart_enabled

	# Website pages don't receive JS translations by default.
	# Inject webshop-specific messages into boot payload for __() in frontend JS.
	boot = context.get("boot") or {}
	boot_messages = boot.get("__messages") or {}
	boot_messages.update(get_website_messages())
	boot["__messages"] = boot_messages
	context["boot"] = boot


def get_website_messages():
	lang = frappe.local.lang or "en"
	cache_key = f"webshop_website_messages::{lang}"
	cached = frappe.cache().get_value(cache_key)
	if cached:
		return cached

	messages = {}
	for message_data in get_messages_for_app("webshop", deduplicate=False):
		source_text = ""
		translation_context = None

		if isinstance(message_data, tuple):
			if len(message_data) >= 2:
				source_text = message_data[1]
			if len(message_data) >= 3:
				translation_context = message_data[2]
		elif isinstance(message_data, str):
			source_text = message_data

		if not source_text:
			continue

		key = (
			f"{source_text}:{translation_context}"
			if translation_context
			else source_text
		)
		messages[key] = _(source_text, context=translation_context)

	frappe.cache().set_value(cache_key, messages)
	return messages


def is_customer():
	if frappe.session.user and frappe.session.user != "Guest":
		contact_name = frappe.get_value("Contact", {"email_id": frappe.session.user})
		if contact_name:
			contact = frappe.get_doc("Contact", contact_name)
			for link in contact.links:
				if link.link_doctype == "Customer":
					return True

		return False
