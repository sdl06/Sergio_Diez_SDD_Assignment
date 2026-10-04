const search = document.querySelector("[data-roster-search]");
if (search) {
  search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    document.querySelectorAll("[data-roster-row]").forEach((row) => {
      row.hidden = !row.textContent.toLowerCase().includes(query);
    });
  });
}
