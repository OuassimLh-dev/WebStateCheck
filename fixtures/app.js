// Research fixture only: the "buggy" mode contains two deliberate defects.
const mode = new URLSearchParams(window.location.search).get("mode") === "fixed" ? "fixed" : "buggy";
const input = document.querySelector("#query");
const button = document.querySelector("#search");
const status = document.querySelector("#status");
const error = document.querySelector("#error");
const results = document.querySelector("#results");

let latestRequestId = 0;
// Observability for controlled experiments, not a part of either defect.
window.__research = { mode, started: [], completed: [] };

async function search(query) {
  const requestId = ++latestRequestId;
  window.__research.started.push({ requestId, query });
  status.textContent = "Loading...";
  error.textContent = "";

  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    window.__research.completed.push({ requestId, query, outcome: "success" });

    // BUG 1 in buggy mode: older replies can overwrite a newer query.
    if (mode === "fixed" && requestId !== latestRequestId) return;
    results.textContent = `Results for: ${data.query}`;
    if (mode === "buggy") status.textContent = "";
  } catch (e) {
    window.__research.completed.push({ requestId, query, outcome: "error" });
    if (mode === "fixed" && requestId !== latestRequestId) return;
    error.textContent = `Search failed: ${e.message}`;
    // BUG 2 in buggy mode: failing requests leave "Loading..." visible.
  } finally {
    // Fixed mode clears loading on BOTH success and failure, only for newest request.
    if (mode === "fixed" && requestId === latestRequestId) status.textContent = "";
  }
}

button.addEventListener("click", () => { void search(input.value.trim()); });
input.addEventListener("keydown", event => {
  if (event.key === "Enter") { void search(input.value.trim()); }
});
