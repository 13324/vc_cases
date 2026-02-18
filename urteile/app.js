const list = document.getElementById("urteile-list");
const countEl = document.getElementById("count");
const searchInput = document.getElementById("search");
const tagFiltersEl = document.getElementById("tag-filters");

let activeTag = null;
let currentSort = "date";

function getAllTags() {
    const tags = new Set();
    urteile.forEach(u => (u.tags || []).forEach(t => tags.add(t)));
    return [...tags].sort();
}

function renderTagFilters() {
    const allTags = getAllTags();
    tagFiltersEl.innerHTML = allTags.map(tag =>
        `<button class="tag-pill${activeTag === tag ? " active" : ""}" data-tag="${tag}">${tag}</button>`
    ).join("");
}

tagFiltersEl.addEventListener("click", (e) => {
    const pill = e.target.closest(".tag-pill");
    if (!pill) return;
    const tag = pill.dataset.tag;
    activeTag = activeTag === tag ? null : tag;
    renderTagFilters();
    renderList(filterAndSort());
});

function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function filterItems() {
    const q = searchInput.value.toLowerCase();
    return urteile.filter(u => {
        const matchesSearch = !q ||
            (u.caseName || "").toLowerCase().includes(q) ||
            (u.court || "").toLowerCase().includes(q) ||
            (u.docketNumber || "").toLowerCase().includes(q) ||
            (u.dateDecided || "").includes(q) ||
            (u.tags || []).some(t => t.toLowerCase().includes(q)) ||
            (u.leitsaetze || "").toLowerCase().includes(q);
        const matchesTag = !activeTag ||
            (u.tags || []).includes(activeTag);
        return matchesSearch && matchesTag;
    });
}

function sortItems(items) {
    if (currentSort === "court") {
        return [...items].sort((a, b) =>
            (a.court || "").localeCompare(b.court || "", "de") ||
            (b.dateDecided || "").localeCompare(a.dateDecided || "")
        );
    }
    return [...items].sort((a, b) =>
        (b.dateDecided || "").localeCompare(a.dateDecided || "")
    );
}

function filterAndSort() {
    return sortItems(filterItems());
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatLeitsaetze(text) {
    if (!text) return "";
    return text.split("\n").filter(l => l.trim()).map(l =>
        `<p>${escapeHtml(l.trim())}</p>`
    ).join("");
}

function renderCard(u) {
    const hasDetails = u.leitsaetze || u.kommentar;
    return `
    <div class="card${hasDetails ? " has-details" : ""}" ${hasDetails ? `onclick="toggleDetails(this)"` : ""}>
        <div class="card-header">
            <div>
                <div class="card-court">${u.court || ""}</div>
                <div class="card-title">
                    ${u.url ? `<a href="${u.url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${u.caseName}</a>` : u.caseName}
                </div>
                <div class="card-meta">
                    <span>Az. ${u.docketNumber || "\u2013"}</span>
                    <span>${formatDate(u.dateDecided)}</span>
                </div>
                ${(u.tags || []).length ? `<div class="card-tags">${u.tags.map(t => `<span class="card-tag">${t}</span>`).join("")}</div>` : ""}
            </div>
            ${hasDetails ? `<span class="card-chevron">\u25B6</span>` : ""}
        </div>
        ${hasDetails ? `<div class="card-details">
            ${u.leitsaetze ? `<div class="detail-section"><h3>Leits\u00e4tze</h3>${formatLeitsaetze(u.leitsaetze)}</div>` : ""}
            ${u.kommentar ? `<div class="detail-section"><h3>Kommentar</h3>${formatLeitsaetze(u.kommentar)}</div>` : ""}
        </div>` : ""}
    </div>`;
}

function renderList(items) {
    countEl.textContent = `${items.length} Entscheidung${items.length !== 1 ? "en" : ""}`;

    if (items.length === 0) {
        list.innerHTML = '<div class="no-results">Keine Ergebnisse gefunden.</div>';
        return;
    }

    if (currentSort === "court") {
        let html = "";
        let lastCourt = null;
        items.forEach(u => {
            const court = u.court || "Unbekannt";
            if (court !== lastCourt) {
                html += `<div class="court-group-header">${court}</div>`;
                lastCourt = court;
            }
            html += renderCard(u);
        });
        list.innerHTML = html;
    } else {
        list.innerHTML = items.map(renderCard).join("");
    }
}

function toggleDetails(card) {
    card.classList.toggle("open");
}

// Sort toggle
document.querySelectorAll(".sort-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        currentSort = btn.dataset.sort;
        document.querySelectorAll(".sort-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        renderList(filterAndSort());
    });
});

searchInput.addEventListener("input", () => renderList(filterAndSort()));

renderTagFilters();
renderList(filterAndSort());
