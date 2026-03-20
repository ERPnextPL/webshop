if (!window.webshop) window.webshop = {}
if (!frappe.boot) frappe.boot = {}
if (!frappe._messages) frappe._messages = {}

const bootMessages = frappe.boot.__messages
if (bootMessages && typeof bootMessages === "object") {
	for (const key of Object.keys(bootMessages)) {
		if (["__proto__", "constructor", "prototype"].includes(key)) continue
		frappe._messages[key] = bootMessages[key]
	}
}
