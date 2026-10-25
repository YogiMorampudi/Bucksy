/* ── Bucksy app.js ── */

// Theme toggle
const toggle = document.getElementById("themeToggle");
if (toggle) {
  const apply = (mode) => {
    document.body.classList.toggle("light-mode", mode === "light");
    toggle.textContent = mode === "light" ? "●" : "◐";
  };
  const saved = localStorage.getItem("bucksy-theme") || "dark";
  apply(saved);
  toggle.addEventListener("click", () => {
    const next = document.body.classList.contains("light-mode") ? "dark" : "light";
    apply(next);
    localStorage.setItem("bucksy-theme", next);
  });
}

// Auto-dismiss flash messages
document.querySelectorAll(".flash").forEach((el) => {
  setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateY(-6px)"; }, 3800);
  setTimeout(() => el.remove(), 4300);
});

// Close modals on Escape
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document.querySelectorAll(".modal-overlay.show").forEach((modal) => {
      modal.classList.remove("show");
    });
  }
});

// Sidebar: collapse text on small screens (already handled by CSS)
// Mark today's date inputs with max=today to prevent future dating
document.querySelectorAll("input[type='date']").forEach((el) => {
  if (!el.max && !el.name?.includes("to")) {
    // allow future dates for transaction scheduling
  }
});

// ── Password Visibility Toggle & Live Strength Meter ──
window.togglePasswordVisibility = function(btn, inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const isPassword = input.type === "password";
  input.type = isPassword ? "text" : "password";
  btn.textContent = isPassword ? "👁" : "🙈";
  btn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
};

window.updatePasswordStrength = function(password, fillId, textId) {
  const fill = document.getElementById(fillId);
  const text = document.getElementById(textId);
  if (!fill || !text) return;

  if (!password) {
    fill.style.width = "0%";
    text.textContent = "";
    return;
  }

  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;

  if (score <= 1) {
    fill.style.width = "25%";
    fill.style.backgroundColor = "var(--red)";
    text.textContent = "Weak (requires at least 8 chars with letters & numbers)";
    text.style.color = "var(--red)";
  } else if (score <= 3) {
    fill.style.width = "65%";
    fill.style.backgroundColor = "var(--amber)";
    text.textContent = "Moderate (add uppercase or symbols for stronger security)";
    text.style.color = "var(--amber)";
  } else {
    fill.style.width = "100%";
    fill.style.backgroundColor = "var(--green)";
    text.textContent = "Strong password ✓";
    text.style.color = "var(--green)";
  }
};

