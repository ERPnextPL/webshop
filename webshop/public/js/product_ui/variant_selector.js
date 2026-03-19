frappe.provide("webshop.product_ui");

class VariantSelector {
	constructor(wrapper) {
		this.$root = $(wrapper);
		this.itemCode = this.$root.data("item-code");
		this.itemName = this.$root.data("item-name");
		this.mode = this.$root.data("ui-mode") || "b2c";
		this.enableCheckout = Boolean(this.$root.data("enable-checkout"));
		this.instanceNamespace = `.variant-selector-${Math.random().toString(36).slice(2, 10)}`;
		this.config = null;
		this.currentSecondaryAttributes = [];
		this.rows = [];

		this.init();
	}

	async init() {
		try {
			this.config = await this.call(
				"webshop.webshop.variant_selector.utils.get_variant_selector_config",
				{ item_code: this.itemCode }
			);

			if (!this.config?.attributes?.length) {
				this.$root.remove();
				return;
			}

			if (this.mode === "b2b" && this.config.primary_attributes.length) {
				this.renderB2B();
			} else {
				this.renderB2C();
			}
		} catch (error) {
			this.showError();
		}
	}

	call(method, args) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method,
				args,
				callback: (r) => resolve(r.message),
				error: reject,
			});
		});
	}

	renderB2C() {
		const attributeFields = this.config.attributes
			.map((attribute) => this.getB2CFieldHtml(attribute))
			.join("");

		this.$root.find(".variant-selector__content").html(`
			<div class="variant-selector__section">
				${attributeFields}
			</div>
			<div class="variant-selector__status"></div>
		`);

		this.$root.off(".variant-selector");
		this.$root.on("change.variant-selector", ".variant-selector__select", () => {
			this.updateB2CSelection();
		});
		this.$root.on("click.variant-selector", ".variant-selector__clear", (e) => {
			e.preventDefault();
			this.clearB2CSelection();
		});
		this.$root.on("click.variant-selector", ".variant-selector__add-single", (e) => {
			const $button = $(e.currentTarget);
			const itemCode = $button.data("item-code");
			const currentQty = Number($button.data("current-qty") || 0);
			this.addSingleVariant(itemCode, currentQty + 1, $button);
		});
	}

	getB2CFieldHtml(attribute) {
		const options = attribute.values
			.map((value) => `<option value="${this.escapeHtml(value)}">${this.escapeHtml(value)}</option>`)
			.join("");

		return `
			<div class="variant-selector__field" data-attribute="${this.escapeHtml(attribute.attribute)}">
				<label class="variant-selector__label" for="variant-${this.slug(attribute.attribute)}">${this.escapeHtml(attribute.attribute)}</label>
				<select class="form-control variant-selector__select"
					id="variant-${this.slug(attribute.attribute)}"
					data-attribute="${this.escapeHtml(attribute.attribute)}">
					<option value="">${__("Choose {0}", [attribute.attribute])}</option>
					${options}
				</select>
			</div>
		`;
	}

	getSelectedB2CAttributes() {
		const selected = {};
		this.$root.find(".variant-selector__select").each((_, select) => {
			const $select = $(select);
			const value = $select.val();
			if (value) {
				selected[$select.data("attribute")] = value;
			}
		});

		return selected;
	}

	async updateB2CSelection() {
		const selectedAttributes = this.getSelectedB2CAttributes();
		if (!Object.keys(selectedAttributes).length) {
			this.resetB2COptions();
			this.renderB2CStatus();
			return;
		}

		try {
			const response = await this.call(
				"webshop.webshop.variant_selector.utils.get_next_attribute_and_values",
				{
					item_code: this.itemCode,
					selected_attributes: selectedAttributes,
				}
			);

			this.updateB2COptions(response.valid_options_for_attributes || {});
			this.renderB2CStatus(response);
		} catch (error) {
			this.showError();
		}
	}

	resetB2COptions() {
		this.config.attributes.forEach((attribute) => {
			const $select = this.getAttributeSelect(attribute.attribute, ".variant-selector__select");
			const selectedValue = $select.val();
			$select.html(`
				<option value="">${__("Choose {0}", [attribute.attribute])}</option>
				${attribute.values
					.map((value) => {
						const selected = value === selectedValue ? "selected" : "";
						return `<option value="${this.escapeHtml(value)}" ${selected}>${this.escapeHtml(value)}</option>`;
					})
					.join("")}
			`);
		});
	}

	updateB2COptions(validOptionsMap) {
		this.config.attributes.forEach((attribute) => {
			const validOptions = validOptionsMap[attribute.attribute] || attribute.values;
			const $select = this.getAttributeSelect(attribute.attribute, ".variant-selector__select");
			const currentValue = $select.val();
			let hasCurrentValue = false;

			$select.find("option").each((_, option) => {
				const $option = $(option);
				const value = $option.attr("value");
				if (!value) {
					return;
				}

				const isValid = validOptions.includes(value);
				$option.prop("disabled", !isValid);
				if (isValid && value === currentValue) {
					hasCurrentValue = true;
				}
			});

			if (currentValue && !hasCurrentValue) {
				$select.val("");
			}
		});
	}

	renderB2CStatus(response = null) {
		const $status = this.$root.find(".variant-selector__status");
		if (!response) {
			$status.empty();
			return;
		}

		const exactMatch = response.exact_match?.length === 1 ? response.exact_match[0] : "";
		const singleMatch =
			exactMatch ||
			(response.filtered_items_count === 1 && response.filtered_items?.length
				? response.filtered_items[0]
				: "");

		if (!singleMatch) {
			$status.html(`
				<div class="variant-selector__summary">
					<span>${this.escapeHtml(
						response.filtered_items_count === 1
							? __("{0} item found.", [response.filtered_items_count])
							: __("{0} items found.", [response.filtered_items_count])
					)}</span>
					<a href="#" class="variant-selector__clear">${__("Clear Values")}</a>
				</div>
			`);
			return;
		}

		const productInfo = response.product_info || {};
		const price = productInfo.price?.formatted_price_sales_uom || "";
		const currentQty = Number(productInfo.qty || 0);
		const canOrder =
			productInfo.allow_items_not_in_stock ||
			productInfo.on_backorder ||
			!productInfo.is_stock_item ||
			Boolean(productInfo.in_stock);

		$status.html(`
			<div class="variant-selector__summary variant-selector__summary--selected">
				<div>
					<div class="variant-selector__summary-title">${__("Selected Variant")}</div>
					<div class="variant-selector__summary-code">${this.escapeHtml(singleMatch)}</div>
					${price ? `<div class="variant-selector__summary-price">${this.escapeHtml(price)}</div>` : ""}
					<div class="variant-selector__summary-stock">${this.getStockLabel(productInfo)}</div>
				</div>
				<a href="#" class="variant-selector__clear">${__("Clear Values")}</a>
			</div>
			<button class="btn btn-primary variant-selector__add-single"
				data-item-code="${this.escapeHtml(singleMatch)}"
				data-current-qty="${currentQty}"
				${canOrder ? "" : "disabled"}>
				${this.enableCheckout ? __("Add to Cart") : __("Add to Quote")}
			</button>
		`);
	}

	clearB2CSelection() {
		this.$root.find(".variant-selector__select").val("");
		this.resetB2COptions();
		this.renderB2CStatus();
	}

	renderB2B() {
		const filterFields = this.config.primary_attributes
			.map((attributeName) => {
				const attribute = this.config.attributes.find((row) => row.attribute === attributeName);
				if (!attribute) {
					return "";
				}

				return `
					<div class="variant-selector__field variant-selector__primary-multiselect"
						data-attribute="${this.escapeHtml(attributeName)}">
						<label class="variant-selector__label" for="filter-${this.slug(attributeName)}">${this.escapeHtml(attributeName)}</label>
						<button type="button"
							class="form-control variant-selector__primary-trigger"
							id="filter-${this.slug(attributeName)}"
							data-attribute="${this.escapeHtml(attributeName)}"
							aria-expanded="false">
							<span class="variant-selector__primary-trigger-text">
								${this.escapeHtml(__("Choose {0}", [attributeName]))}
							</span>
						</button>
						<div class="variant-selector__primary-dropdown">
							${attribute.values
								.map(
									(value) => `
										<label class="variant-selector__primary-option">
											<input type="checkbox"
												class="variant-selector__primary-filter"
												data-attribute="${this.escapeHtml(attributeName)}"
												value="${this.escapeHtml(value)}">
											<span>${this.escapeHtml(value)}</span>
										</label>
									`
								)
								.join("")}
						</div>
					</div>
				`;
			})
			.join("");

		this.$root.find(".variant-selector__content").html(`
			<div class="variant-selector__from-price"></div>
			<div class="variant-selector__section variant-selector__section--filters">
				${filterFields}
				<div class="variant-selector__actions">
					<a href="#" class="variant-selector__clear-filters">${__("Clear Values")}</a>
				</div>
			</div>
			<div class="variant-selector__table-state">
				${this.getB2BPlaceholder()}
			</div>
			<div class="variant-selector__table"></div>
			<div class="variant-selector__footer hidden">
				<button class="btn btn-secondary variant-selector__add-multiple">
					${__("Choose product variant(s) above")}
				</button>
			</div>
		`);

		this.$root.off(".variant-selector");
		$(document).off(this.instanceNamespace);
		$(document).on(`click${this.instanceNamespace}`, (e) => {
			if (!$(e.target).closest(this.$root[0]).length) {
				this.closePrimaryFilterDropdowns();
			}
		});
		this.$root.on("click.variant-selector", ".variant-selector__primary-trigger", (e) => {
			e.preventDefault();
			e.stopPropagation();
			const $field = $(e.currentTarget).closest(".variant-selector__primary-multiselect");
			const isOpen = $field.hasClass("is-open");
			this.closePrimaryFilterDropdowns();
			if (!isOpen) {
				$field.addClass("is-open");
				$(e.currentTarget).attr("aria-expanded", "true");
			}
		});
		this.$root.on("click.variant-selector", ".variant-selector__primary-dropdown", (e) => {
			e.stopPropagation();
		});
		this.$root.on("change.variant-selector", ".variant-selector__primary-filter", (e) => {
			const attributeName = $(e.currentTarget).data("attribute");
			this.updatePrimaryFilterTriggerText(attributeName);
			this.updateB2BTable();
		});
		this.$root.on("click.variant-selector", ".variant-selector__clear-filters", (e) => {
			e.preventDefault();
			this.$root.find(".variant-selector__primary-filter").prop("checked", false);
			this.config.primary_attributes.forEach((attributeName) => {
				this.updatePrimaryFilterTriggerText(attributeName);
			});
			this.closePrimaryFilterDropdowns();
			this.rows = [];
			this.renderB2BRows();
		});
		this.$root.on("click.variant-selector", ".variant-qty__btn", (e) => {
			this.updateRowQtyFromButton(e.currentTarget);
		});
		this.$root.on("input.variant-selector", ".variant-qty__input", (e) => {
			this.updateRowQtyFromInput(e.currentTarget);
		});
		this.$root.on("click.variant-selector", ".variant-selector__add-multiple", async (e) => {
			await this.addMultipleVariants($(e.currentTarget));
		});
	}

	getSelectedPrimaryFilters() {
		const selected = {};
		this.$root.find(".variant-selector__primary-multiselect").each((_, field) => {
			const $field = $(field);
			const values = $field
				.find(".variant-selector__primary-filter:checked")
				.map((__, input) => $(input).val())
				.get()
				.filter(Boolean);
			if (values.length) {
				selected[$field.data("attribute")] = values;
			}
		});

		return selected;
	}

	async updateB2BTable() {
		const selectedFilters = this.getSelectedPrimaryFilters();
		if (Object.keys(selectedFilters).length !== this.config.primary_attributes.length) {
			this.rows = [];
			this.renderB2BRows();
			return;
		}

		try {
			const response = await this.call(
				"webshop.webshop.variant_selector.utils.get_variant_rows",
				{
					item_code: this.itemCode,
					selected_filters: selectedFilters,
				}
			);

			this.rows = (response.rows || []).map((row) => {
				return {
					...row,
					qty: 0,
					initial_qty: 0,
					qty_in_cart: Number(row.qty_in_cart || 0),
				};
			});
			this.currentSecondaryAttributes = response.secondary_attributes || [];
			this.renderB2BRows(this.currentSecondaryAttributes);
		} catch (error) {
			this.showError();
		}
	}

	renderB2BRows(secondaryAttributes = this.currentSecondaryAttributes || this.config.secondary_attributes || []) {
		const $state = this.$root.find(".variant-selector__table-state");
		const $table = this.$root.find(".variant-selector__table");
		const $footer = this.$root.find(".variant-selector__footer");

		// Update "From" price
		this.updateFromPrice();

		if (!this.rows.length) {
			$table.empty();
			$footer.addClass("hidden");
			$state.html(this.getB2BEmptyState());
			return;
		}

		const displaySecondaryAttributes = this.getDisplaySecondaryAttributes(secondaryAttributes);
		const headerColumns = [
			`<th class="variant-selector__matrix-head-cell">${__("Size")}</th>`,
			`<th class="variant-selector__matrix-head-cell">${__("Fabric")}</th>`,
			...displaySecondaryAttributes.map(
				(attributeName) =>
					`<th class="variant-selector__matrix-head-cell">${this.escapeHtml(attributeName)}</th>`
			)
		].join("");
		const bodyRows = this.rows
			.map((row) => {
				const rozmiarValue = this.getPreferredAttributeValue(row, ["Rozmiar", "Size"]);
				const tkaninaValue = this.getPreferredAttributeValue(row, ["Tkanina", "Fabric"]);
				const rozmiarCell = `<td class="variant-selector__matrix-cell">${this.escapeHtml(
					this.formatAttributeValue("Rozmiar", rozmiarValue)
				)}</td>`;
				const tkaninaCell = `<td class="variant-selector__matrix-cell">${this.escapeHtml(
					this.formatAttributeValue("Tkanina", tkaninaValue)
				)}</td>`;
				const secondaryCells = displaySecondaryAttributes
					.map(
						(attributeName) =>
							`<td class="variant-selector__matrix-cell">${this.escapeHtml(
								this.formatAttributeValue(attributeName, row.secondary_attributes?.[attributeName] || "—")
							)}</td>`
					)
					.join("");
				const disableMinusAndInput = !row.can_order ? "disabled" : "";
				const disablePlus = row.can_order ? "" : "disabled";
				const stockLabel = this.getStockLabel(row);

				return `
					<tr class="variant-selector__matrix-row" data-item-code="${this.escapeHtml(row.item_code)}">
						${rozmiarCell}
						${tkaninaCell}
						${secondaryCells}
						<td class="variant-selector__matrix-cell">${this.escapeHtml(row.formatted_price || "—")}</td>
						<td class="variant-selector__matrix-cell variant-selector__matrix-cell--qty">
							<div class="variant-qty" data-item-code="${this.escapeHtml(row.item_code)}">
								<button type="button" class="variant-qty__btn" data-direction="-1" ${disableMinusAndInput}>
									${this.getQtyButtonIcon(-1)}
								</button>
								<div class="variant-qty__input-wrap">
									<input
										type="number"
										min="0"
										step="1"
										pattern="[0-9]*"
										inputmode="numeric"
										class="variant-qty__input"
										data-item-code="${this.escapeHtml(row.item_code)}"
										value="${Number(row.qty || 0)}"
										${disableMinusAndInput}
									>
								</div>
								<button type="button" class="variant-qty__btn" data-direction="1" ${disablePlus}>
									${this.getQtyButtonIcon(1)}
								</button>
							</div>
							${stockLabel ? `<div class="variant-qty__stock">${this.escapeHtml(stockLabel)}</div>` : ""}
						</td>
					</tr>
				`;
			})
			.join("");

		$state.empty();
		$table.html(`
			<div class="table-responsive variant-selector__table-wrap">
				<table class="table variant-selector__matrix">
					<thead class="variant-selector__matrix-head">
						<tr class="variant-selector__matrix-head-row">
							${headerColumns}
							<th class="variant-selector__matrix-head-cell">${__("Price")}</th>
							<th class="variant-selector__matrix-head-cell">${__("Quantity")}</th>
						</tr>
					</thead>
					<tbody class="variant-selector__matrix-body">${bodyRows}</tbody>
				</table>
			</div>
		`);
		$footer.removeClass("hidden");
		this.updateFooterState();
	}

	updateFooterState() {
		const $btn = this.$root.find(".variant-selector__add-multiple");
		if (!$btn.length) return;

		const totalQty = this.rows.reduce((sum, row) => sum + Number(row.qty || 0), 0);
		const changedRows = this.rows.filter(
			(row) => Number(row.qty || 0) !== Number(row.initial_qty || 0)
		);

		if (totalQty === 0 || !changedRows.length) {
			$btn.prop("disabled", true);
			$btn.text(__("Choose product variant(s) above"));
			$btn.removeClass("btn-primary").addClass("btn-secondary");
		} else {
			$btn.prop("disabled", false);
			$btn.text(this.enableCheckout ? __("Add Selected to Cart") : __("Add Selected to Quote"));
			$btn.removeClass("btn-secondary").addClass("btn-primary");
		}

		// Update stock indicator
		this.updateStockIndicator();
	}

	updateStockIndicator() {
		let $indicator = this.$root.find(".variant-selector__stock-indicator");
		if (!$indicator.length) {
			this.$root.find(".variant-selector__footer").after(
				'<div class="variant-selector__stock-indicator"></div>'
			);
			$indicator = this.$root.find(".variant-selector__stock-indicator");
		}

		const totalStock = this.rows.reduce(
			(sum, row) => sum + Number(row.stock_qty || 0), 0
		);
		const hasAnyStock = this.rows.some((row) => Number(row.in_stock) === 1);

		if (hasAnyStock) {
			$indicator.html(
				`<span class="variant-selector__stock-dot variant-selector__stock-dot--limited"></span> ${this.escapeHtml(
					__("Limited quantity available ({0} in stock)", [totalStock])
				)}`
			);
		} else {
			$indicator.html(
				`<span class="variant-selector__stock-dot variant-selector__stock-dot--out"></span> ${this.escapeHtml(
					__("Limited quantity available ({0} in stock)", [totalStock])
				)}`
			);
		}
	}

	updateFromPrice() {
		const $priceEl = this.$root.find(".variant-selector__from-price");
		if (!$priceEl.length) return;

		const pricedRows = this.rows.filter((row) => Number(row.price_number || 0) > 0);
		if (!pricedRows.length) {
			$priceEl.empty();
			return;
		}

		pricedRows.sort((a, b) => Number(a.price_number) - Number(b.price_number));
		const minRow = pricedRows[0];

		$priceEl.html(`
			<div class="variant-selector__from-price-value">
				${__("From")} ${this.escapeHtml(minRow.formatted_price)}
			</div>
			<div class="variant-selector__from-price-vat">${__("Excl. VAT")}</div>
		`);
	}

	getB2BPlaceholder() {
		if (this.config.primary_attributes.length >= 2) {
			return `<div class="variant-selector__placeholder">${__(
				"Select one or more values for {0} and {1} to see matching variants.",
				[this.config.primary_attributes[0], this.config.primary_attributes[1]]
			)}</div>`;
		}

		if (this.config.primary_attributes.length === 1) {
			return `<div class="variant-selector__placeholder">${__(
				"Select one or more values for {0}.",
				[this.config.primary_attributes[0]]
			)}</div>`;
		}

		return "";
	}

	getB2BEmptyState() {
		if (!this.areAllPrimaryFiltersSelected()) {
			return this.getB2BPlaceholder();
		}

		return `<div class="variant-selector__placeholder">${__(
			"No variants available for the selected filters."
		)}</div>`;
	}

	updateRowQtyFromButton(button) {
		const $button = $(button);
		const itemCode = $button.closest(".variant-qty").data("item-code");
		const direction = Number($button.data("direction") || 0);
		const row = this.rows.find((entry) => entry.item_code === itemCode);
		if (!row) {
			return;
		}

		if (direction > 0 && !row.can_order) {
			return;
		}

		const nextQty = Math.max(0, Number(row.qty || 0) + direction);
		row.qty = nextQty;
		this.getQtyInput(itemCode).val(nextQty);
		this.updateFooterState();
	}

	updateRowQtyFromInput(input) {
		const $input = $(input);
		const itemCode = $input.data("item-code");
		const row = this.rows.find((entry) => entry.item_code === itemCode);
		if (!row) {
			return;
		}

		let nextQty = Math.max(0, Number($input.val() || 0));
		if (!row.can_order) {
			nextQty = 0;
		}

		row.qty = nextQty;
		$input.val(nextQty);
		this.updateFooterState();
	}

	async addMultipleVariants($button) {
		const changedRows = this.rows.filter(
			(row) => Number(row.qty || 0) !== Number(row.initial_qty || 0)
		);
		const totalSelectedQty = this.rows.reduce((total, row) => total + Number(row.qty || 0), 0);

		if (!changedRows.length && totalSelectedQty === 0) {
			frappe.show_alert({
				message: __("Select at least one variant quantity."),
				indicator: "orange",
			});
			return;
		}

		if (!changedRows.length) {
			frappe.show_alert({
				message: this.enableCheckout ? __("Add Selected to Cart") : __("Add Selected to Quote"),
				indicator: "green",
			});
			return;
		}

		$button.prop("disabled", true);

		try {
			for (const row of changedRows) {
				const nextCartQty = Number(row.qty_in_cart || 0) + Number(row.qty || 0);
				await this.updateCart(row.item_code, nextCartQty);
			}

			this.rows = this.rows.map((row) => ({
				...row,
				qty_in_cart: Number(row.qty_in_cart || 0) + Number(row.qty || 0),
				qty: 0,
				initial_qty: 0,
			}));
			this.renderB2BRows();

			frappe.show_alert({
				message: this.enableCheckout ? __("Add Selected to Cart") : __("Add Selected to Quote"),
				indicator: "green",
			});
		} catch (error) {
			this.showError();
		} finally {
			$button.prop("disabled", false);
		}
	}

	updateCart(itemCode, qty) {
		return new Promise((resolve) => {
			webshop.webshop.shopping_cart.update_cart({
				item_code: itemCode,
				qty,
				callback: resolve,
			});
		});
	}

	addSingleVariant(itemCode, qty, $button) {
		$button.prop("disabled", true);
		this.updateCart(itemCode, qty)
			.then(() => {
				$button.data("current-qty", qty);
				frappe.show_alert({
					message: this.enableCheckout ? __("Add to Cart") : __("Add to Quote"),
					indicator: "green",
				});
			})
			.catch(() => {
				this.showError();
			})
			.finally(() => {
				$button.prop("disabled", false);
			});
	}

	getStockLabel(productInfo) {
		if (productInfo.on_backorder) {
			return __("Available on backorder");
		}

		if (Number(productInfo.in_stock) === 0 && Number(productInfo.stock_qty || 0) <= 0) {
			return __("Out of stock");
		}

		if (Number(productInfo.in_stock) === 1) {
			if (Number(productInfo.stock_qty || 0) > 0) {
				return `${__("In stock")} (${Number(productInfo.stock_qty)})`;
			}

			return __("In stock");
		}

		return "";
	}

	getQtyButtonIcon(direction) {
		if (direction < 0) {
			return `
				<svg viewBox="0 0 15 15" aria-hidden="true" focusable="false">
					<path d="M2.5 7.5h10"></path>
				</svg>
			`;
		}

		return `
			<svg viewBox="0 0 15 15" aria-hidden="true" focusable="false">
				<path d="M7.5 2.5v10M2.5 7.5h10"></path>
			</svg>
		`;
	}

	slug(value) {
		return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
	}

	getAttributeSelect(attributeName, selector) {
		return this.$root
			.find(selector)
			.filter((_, element) => $(element).data("attribute") === attributeName)
			.first();
	}

	getQtyInput(itemCode) {
		return this.$root
			.find(".variant-qty__input")
			.filter((_, element) => $(element).data("item-code") === itemCode)
			.first();
	}

	getPrimaryFilterField(attributeName) {
		return this.$root
			.find(".variant-selector__primary-multiselect")
			.filter((_, element) => $(element).data("attribute") === attributeName)
			.first();
	}

	updatePrimaryFilterTriggerText(attributeName) {
		const $field = this.getPrimaryFilterField(attributeName);
		if (!$field.length) {
			return;
		}

		const selectedValues = $field
			.find(".variant-selector__primary-filter:checked")
			.map((_, input) => $(input).val())
			.get();
		const $text = $field.find(".variant-selector__primary-trigger-text");

		if (!selectedValues.length) {
			$text.text(__("Choose {0}", [attributeName]));
			return;
		}

		if (selectedValues.length <= 2) {
			$text.text(selectedValues.join(", "));
			return;
		}

		$text.text(__("{0} selected", [selectedValues.length]));
	}

	closePrimaryFilterDropdowns() {
		this.$root.find(".variant-selector__primary-multiselect").removeClass("is-open");
		this.$root.find(".variant-selector__primary-trigger").attr("aria-expanded", "false");
	}

	areAllPrimaryFiltersSelected() {
		return Object.keys(this.getSelectedPrimaryFilters()).length === this.config.primary_attributes.length;
	}

	showError() {
		frappe.show_alert({
			message: __("Something went wrong. Please refresh or contact us."),
			indicator: "red",
		});
	}

	getDisplaySecondaryAttributes(secondaryAttributes) {
		return (secondaryAttributes || []).filter((name) => {
			const normalized = this.normalizeAttributeName(name);
			return normalized !== "rozmiar" && normalized !== "size" && normalized !== "tkanina" && normalized !== "fabric";
		});
	}

	getPreferredAttributeValue(row, candidates) {
		const attributes = row?.attributes || {};
		for (const candidate of candidates) {
			const normalizedCandidate = this.normalizeAttributeName(candidate);
			const exact = attributes[candidate];
			if (exact) return exact;
			const matchedKey = Object.keys(attributes).find(
				(key) => this.normalizeAttributeName(key) === normalizedCandidate
			);
			if (matchedKey && attributes[matchedKey]) {
				return attributes[matchedKey];
			}
		}
		return "—";
	}

	normalizeAttributeName(value) {
		return `${value || ""}`.trim().toLowerCase();
	}

	formatAttributeValue(attributeName, value) {
		if (value === "—") return value;
		if (attributeName === "Stelaż" || attributeName === "Materac") {
			let prefix = attributeName + " ";
			if (value.startsWith(prefix)) {
				value = value.slice(prefix.length);
			}
			value = value.charAt(0).toUpperCase() + value.slice(1);
		}
		return value;
	}

	escapeHtml(value) {
		return frappe.utils.escape_html(`${value ?? ""}`);
	}
}

frappe.ready(() => {
	$(".variant-selector").each((_, element) => {
		new VariantSelector(element);
	});
});
