if (!window.webshop) window.webshop = {}
if (!frappe.boot) frappe.boot = {}
if (!frappe._messages) frappe._messages = {}
if (frappe.boot.__messages) Object.assign(frappe._messages, frappe.boot.__messages)
