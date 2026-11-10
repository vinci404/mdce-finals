document.addEventListener("DOMContentLoaded", () => {
  const timers = new Map();
  const seqs = new Map();

  const hintFor = (input) => {
    const anchor = input.closest(".pw") || input;
    let hint = anchor.nextElementSibling;
    if (!hint || !hint.classList.contains("hint")) {
      hint = document.createElement("small");
      hint.className = "hint";
      anchor.insertAdjacentElement("afterend", hint);
    }
    return hint;
  };

  const show = (input, errors) => {
    hintFor(input).textContent = errors.join("\n");
    input.classList.toggle("invalid", errors.length > 0);
    input.classList.toggle("valid", errors.length === 0 && input.value !== "");
  };

  // Asks the server (/check_field) if this one box is correct
  const checkField = async (input) => {
    const seq = (seqs.get(input) || 0) + 1;
    seqs.set(input, seq);
    const body = new URLSearchParams();
    body.append("field", input.dataset.field);
    body.append("value", input.value);
    if (input.dataset.field === "confirm") {
      body.append("other", document.getElementById("password").value);
    }
    try {
      const res = await fetch("/check_field", { method: "POST", body });
      const data = await res.json();
      if (seq !== seqs.get(input)) return;   // a newer check is running
      show(input, data.errors || []);
    } catch (e) {
      show(input, ["Could not check this right now."]);
    }
  };

  const later = (input, ms) => {
    clearTimeout(timers.get(input));
    timers.set(input, setTimeout(() => checkField(input), ms));
  };

  document.querySelectorAll("[data-field]").forEach((input) => {
    input.addEventListener("input", () => {
      later(input, 400);
      if (input.dataset.field === "password") {
        const c = document.getElementById("confirm");
        if (c && c.value) later(c, 400);
      }
    });
    input.addEventListener("blur", () => {
      if (input.value !== "") later(input, 0);
    });
  });

  // Show / Hide password buttons
  document.querySelectorAll(".show-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const t = document.getElementById(btn.dataset.target);
      t.type = t.type === "password" ? "text" : "password";
      btn.textContent = t.type === "password" ? "Show" : "Hide";
    });
  });

  // "Other (type it)" boxes
  document.querySelectorAll("select[data-other]").forEach((sel) => {
    const box = document.getElementById(sel.dataset.other);
    const sync = () => { box.hidden = sel.value !== "Other"; };
    sel.addEventListener("change", sync);
    sync();
  });
});