// Update footer copyright year dynamically.
const yearTarget = document.getElementById("current-year");
if (yearTarget) {
  yearTarget.textContent = new Date().getFullYear();
}

// Enable smooth scroll for internal anchor links.
const anchorLinks = document.querySelectorAll('a[href^="#"]');
anchorLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    const href = link.getAttribute("href");
    if (!href || href === "#") {
      return;
    }
    const targetElement = document.querySelector(href);
    if (targetElement) {
      event.preventDefault();
      targetElement.scrollIntoView({ behavior: "smooth" });
    }
  });
});
