const tripBuilder = document.querySelector("[data-trip-builder]");

if (tripBuilder) {
  const form = tripBuilder.querySelector("[data-trip-form]");
  const checkboxes = [...tripBuilder.querySelectorAll("[data-child-checkbox]")];
  const selectAll = tripBuilder.querySelector("[data-select-all]");
  const search = tripBuilder.querySelector("[data-child-search]");
  const routeSelect = tripBuilder.querySelector("[data-route-select]");
  const rows = [...tripBuilder.querySelectorAll("[data-child-row]")];
  const modal = tripBuilder.querySelector("[data-review-modal]");

  const updateSummary = () => {
    const selectedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
    tripBuilder.querySelector("[data-selected-count]").textContent = selectedCount;
    tripBuilder.querySelector("[data-summary-count]").textContent = selectedCount;

    const tripName = form.elements.trip_name.value.trim();
    const route = routeSelect.value ? routeSelect.selectedOptions[0].textContent : "";
    const date = form.elements.date.value;
    const time = form.elements.time.value;
    tripBuilder.querySelector("[data-summary-name]").textContent = tripName || "Untitled trip";
    tripBuilder.querySelector("[data-summary-route]").textContent = route || "Not selected";
    tripBuilder.querySelector("[data-summary-schedule]").textContent = date && time ? `${date} at ${time}` : "Not scheduled";

    const visible = checkboxes.filter((checkbox) => !checkbox.closest("[data-child-row]").classList.contains("hidden"));
    selectAll.checked = visible.length > 0 && visible.every((checkbox) => checkbox.checked);
    selectAll.indeterminate = visible.some((checkbox) => checkbox.checked) && !selectAll.checked;
  };

  form.addEventListener("input", updateSummary);
  routeSelect.addEventListener("change", () => {
    const url = new URL(window.location.href);
    if (routeSelect.value) url.searchParams.set("route", routeSelect.value);
    else url.searchParams.delete("route");
    window.location.assign(url.toString());
  });
  checkboxes.forEach((checkbox) => checkbox.addEventListener("change", updateSummary));

  selectAll.addEventListener("change", () => {
    checkboxes.forEach((checkbox) => {
      if (!checkbox.closest("[data-child-row]").classList.contains("hidden")) checkbox.checked = selectAll.checked;
    });
    updateSummary();
  });

  search.addEventListener("input", () => {
    const query = search.value.toLowerCase().trim();
    let visibleRows = 0;
    rows.forEach((row) => {
      const matches = row.dataset.searchValue.includes(query);
      row.classList.toggle("hidden", !matches);
      if (matches) visibleRows += 1;
    });
    tripBuilder.querySelector("[data-empty-search]").classList.toggle("hidden", visibleRows !== 0);
    updateSummary();
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    let valid = true;
    ["trip_name", "route", "monitor", "date", "time"].forEach((fieldName) => {
      const field = form.elements[fieldName];
      const error = tripBuilder.querySelector(`[data-error-for="${fieldName}"]`);
      const fieldValid = Boolean(field.value.trim());
      error.classList.toggle("hidden", fieldValid);
      field.classList.toggle("border-rose-500", !fieldValid);
      valid = valid && fieldValid;
    });

    const hasChildren = checkboxes.some((checkbox) => checkbox.checked);
    tripBuilder.querySelector("[data-children-error]").classList.toggle("hidden", hasChildren);
    valid = valid && hasChildren;

    if (!valid) {
      form.querySelector(".border-rose-500, [data-children-error]:not(.hidden)")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    modal.classList.remove("hidden");
    modal.classList.add("flex");
    modal.querySelector("[data-close-modal]").focus();
  });

  modal.querySelector("[data-close-modal]").addEventListener("click", () => {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  });

  updateSummary();
}
