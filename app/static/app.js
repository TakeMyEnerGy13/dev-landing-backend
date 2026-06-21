const form = document.getElementById("contact-form");
const result = document.getElementById("result");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = Object.fromEntries(new FormData(form).entries());
  result.hidden = false;
  result.textContent = "Sending…";
  try {
    const res = await fetch("/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 429) { result.textContent = "Too many requests — please wait a bit."; return; }
    if (res.status === 422) { result.textContent = "Please check your inputs."; return; }
    const data = await res.json();
    const s = data.analysis.sentiment;
    result.innerHTML = `${data.message} <span class="badge ${s}">${s}</span>`;
    form.reset();
  } catch {
    result.textContent = "Network error — please try again.";
  }
});
