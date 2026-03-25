// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// JS exclusive to /cart page
frappe.provide("webshop.webshop.shopping_cart");
var shopping_cart = webshop.webshop.shopping_cart;

$.extend(shopping_cart, {
	show_error: function(title, text) {
		$("#cart-container").html('<div class="msg-box"><h4>' +
			title + '</h4><p class="text-muted">' + text + '</p></div>');
	},

	normalize_qty: function($input) {
		const mustBeWholeNumber = Number($input.data("must-be-whole-number") || 0);
		let qty = Number.parseFloat(String($input.val() || "").replace(",", "."));

		if (!Number.isFinite(qty) || qty < 1) {
			qty = 1;
		}

		if (mustBeWholeNumber && !Number.isInteger(qty)) {
			qty = Math.round(qty);
			frappe.show_alert({
				message: __("This item can only be ordered in whole numbers."),
				indicator: "orange"
			});
		}

		$input.val(qty);
		return qty;
	},

	bind_events: function() {
		shopping_cart.bind_place_order();
		shopping_cart.bind_request_quotation();
		shopping_cart.bind_export_csv();
		shopping_cart.bind_empty_cart();
		shopping_cart.bind_change_qty();
		shopping_cart.bind_remove_cart_item();
		shopping_cart.bind_change_notes();
		shopping_cart.bind_toggle_notes();
		shopping_cart.bind_coupon_code();
		shopping_cart.bind_remove_coupon_code();
	},

	bind_place_order: function() {
		$(".btn-place-order").on("click", function() {
			shopping_cart.place_order(this);
		});
	},

	bind_request_quotation: function() {
		$('.btn-request-for-quotation').on('click', function() {
			shopping_cart.request_quotation(this);
		});
	},

	bind_export_csv: function() {
		$('.btn-export-csv').on('click', function() {
			shopping_cart.export_csv(this);
		});
	},

	bind_empty_cart: function() {
		$('.btn-empty-cart').on('click', function() {
			shopping_cart.empty_cart(this);
		});
	},

	bind_change_qty: function() {
		// bind update on input change
		$(".cart-items-list").on("change", ".cart-qty", function() {
			const $input = $(this);
			var item_code = $input.attr("data-item-code");
			var newVal = shopping_cart.normalize_qty($input);
			shopping_cart.shopping_cart_update({item_code, qty: newVal});
		});

		// bind qty buttons
		$(".cart-items-list").on('click', '.qty-btn', function () {
			var btn = $(this),
				adjuster = btn.closest('.qty-adjuster'),
				input = adjuster.find('.qty-input'),
				oldValue = input.val().trim(),
				newVal = 0;

			if (btn.hasClass('qty-btn-plus')) {
				newVal = parseInt(oldValue) + 1;
			} else if (btn.hasClass('qty-btn-minus')) {
				if (oldValue > 1) {
					newVal = parseInt(oldValue) - 1;
				} else {
					return;
				}
			}
			
			input.val(newVal);
			var item_code = input.attr("data-item-code");
			shopping_cart.shopping_cart_update({
				item_code,
				qty: newVal
			});
		});
	},

	bind_change_notes: function() {
		$('.cart-items-list').on('change', 'textarea', function() {
			const $textarea = $(this);
			const item_code = $textarea.attr('data-item-code');
			const $card = $textarea.closest('.cart-item-card');
			const qty = $card.find('.cart-qty').val();
			const notes = $textarea.val();
			shopping_cart.shopping_cart_update({
				item_code,
				qty,
				additional_notes: notes
			});
		});
	},

	bind_toggle_notes: function() {
		$('.cart-items-list').on('click', '.add-note-btn', function(e) {
			e.preventDefault();
			const $btn = $(this);
			const $card = $btn.closest('.cart-item-card');
			const $notes = $card.find('.cart-item-notes');
			
			$notes.toggleClass('show');
			if ($notes.hasClass('show')) {
				$notes.find('textarea').focus();
			}
		});
	},

	bind_remove_cart_item: function() {
		$(".cart-items-list").on("click", ".remove-cart-item", (e) => {
			e.preventDefault();
			const $remove_btn = $(e.currentTarget);
			var item_code = $remove_btn.data("item-code");

			shopping_cart.shopping_cart_update({
				item_code: item_code,
				qty: 0
			});
		});
	},

	render_tax_row: function($cart_taxes, doc, shipping_rules) {
		var shipping_selector;
		if(shipping_rules) {
			shipping_selector = '<select class="form-control">' + $.map(shipping_rules, function(rule) {
				return '<option value="' + rule[0] + '">' + rule[1] + '</option>' }).join("\n") +
			'</select>';
		}

		var $tax_row = $(repl('<div class="row">\
			<div class="col-md-9 col-sm-9">\
				<div class="row">\
					<div class="col-md-9 col-md-offset-3">' +
					(shipping_selector || '<p>%(description)s</p>') +
					'</div>\
				</div>\
			</div>\
			<div class="col-md-3 col-sm-3 text-right">\
				<p' + (shipping_selector ? ' style="margin-top: 5px;"' : "") + '>%(formatted_tax_amount)s</p>\
			</div>\
		</div>', doc)).appendTo($cart_taxes);

		if(shipping_selector) {
			$tax_row.find('select option').each(function(i, opt) {
				if($(opt).html() == doc.description) {
					$(opt).attr("selected", "selected");
				}
			});
			$tax_row.find('select').on("change", function() {
				shopping_cart.apply_shipping_rule($(this).val(), this);
			});
		}
	},

	apply_shipping_rule: function(rule, btn) {
		return frappe.call({
			btn: btn,
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.apply_shipping_rule",
			args: { shipping_rule: rule },
			callback: function(r) {
				if(!r.exc) {
					shopping_cart.render(r.message);
				}
			}
		});
	},

	place_order: function(btn) {
		shopping_cart.freeze();

		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.place_order",
			btn: btn,
			callback: function(r) {
				if(r.exc) {
					shopping_cart.unfreeze();
					var msg = "";
					if(r._server_messages) {
						msg = JSON.parse(r._server_messages || []).join("<br>");
					}

					$("#cart-error")
						.empty()
						.html(msg || frappe._("Something went wrong!"))
						.toggle(true);
				} else {
					$(btn).hide();
					window.location.href = '/orders/' + encodeURIComponent(r.message);
				}
			}
		});
	},

	request_quotation: function(btn) {
		shopping_cart.freeze();

		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.request_for_quotation",
			btn: btn,
			callback: function(r) {
				if(r.exc) {
					shopping_cart.unfreeze();
					var msg = "";
					if(r._server_messages) {
						msg = JSON.parse(r._server_messages || []).join("<br>");
					}

					$("#cart-error")
						.empty()
						.html(msg || frappe._("Something went wrong!"))
						.toggle(true);
				} else {
					$(btn).hide();
					window.location.href = '/quotations/' + encodeURIComponent(r.message);
				}
			}
		});
	},

	export_csv: function(btn) {
		shopping_cart.freeze();

		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.export_cart_csv",
			btn: btn,
			callback: function(r) {
				shopping_cart.unfreeze();
				if(!r.exc && r.message) {
					// Trigger download
					var link = document.createElement('a');
					link.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(r.message);
					link.download = 'cart_' + frappe.utils.get_today() + '.csv';
					document.body.appendChild(link);
					link.click();
					document.body.removeChild(link);
				} else {
					var msg = "";
					if(r._server_messages) {
						msg = JSON.parse(r._server_messages || []).join("<br>");
					}
					$("#cart-error")
						.empty()
						.html(msg || frappe._("Something went wrong!"))
						.toggle(true);
				}
			}
		});
	},

	empty_cart: function(btn) {
		if(!confirm(frappe._("Are you sure you want to empty your cart?"))) {
			return;
		}

		shopping_cart.freeze();

		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.empty_cart",
			btn: btn,
			callback: function(r) {
				shopping_cart.unfreeze();
				if(!r.exc) {
					window.location.href = '/cart';
				} else {
					var msg = "";
					if(r._server_messages) {
						msg = JSON.parse(r._server_messages || []).join("<br>");
					}

					$("#cart-error")
						.empty()
						.html(msg || frappe._("Something went wrong!"))
						.toggle(true);
				}
			}
		});
	},

	bind_coupon_code: function() {
		$(".bt-coupon").on("click", function() {
			shopping_cart.apply_coupon_code(this);
		});
	},

	apply_coupon_code: function(btn) {
		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.apply_coupon_code",
			btn: btn,
			args : {
				applied_code : $('.txtcoupon').val(),
				applied_referral_sales_partner: $('.txtreferral_sales_partner').val()
			},
			callback: function(r) {
				if (r && r.message){
					location.reload();
				}
			}
		});
	},

	bind_remove_coupon_code: function() {
		$(".bt-remove-coupon-code").on("click", function() {
			shopping_cart.remove_coupon_code(this);
		});
	},
	remove_coupon_code: function(btn) {
		return frappe.call({
			type: "POST",
			method: "webshop.webshop.shopping_cart.cart.remove_coupon_code",
			btn: btn,
			callback: function(r) {
				if (r && r.message){
					location.reload();
				}
			}
		});
	},

});

frappe.ready(function() {
	if (window.location.pathname === "/cart") {
		$(".cart-icon").hide();
	}
	shopping_cart.parent = $(".cart-container");
	shopping_cart.bind_events();
});

function show_terms() {
	var html = $(".cart-terms").html();
	frappe.msgprint(html);
}
