const form = document.getElementById("contact-form");
const result = document.getElementById("result");
const submit = form.querySelector(".submit");
const submitLabel = form.querySelector(".submit__label");

function show(message, sentiment) {
  result.hidden = false;
  result.textContent = message;
  if (sentiment) {
    const badge = document.createElement("span");
    badge.className = `badge ${sentiment}`;
    badge.textContent = sentiment;
    result.append(" ", badge);
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = Object.fromEntries(new FormData(form).entries());
  submit.disabled = true;
  submitLabel.textContent = "Sending…";
  show("Sending…");

  try {
    const res = await fetch("/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.status === 429) {
      show("Too many requests — please wait a moment and try again.");
      return;
    }
    if (res.status === 422) {
      show("Some fields need attention — please check name, email, phone and message.");
      return;
    }
    if (!res.ok) {
      show("Something went wrong on our side. Please try again shortly.");
      return;
    }

    const data = await res.json();
    show(data.message, data.analysis && data.analysis.sentiment);
    form.reset();
  } catch {
    show("Network error — please check your connection and try again.");
  } finally {
    submit.disabled = false;
    submitLabel.textContent = "Send message";
  }
});
