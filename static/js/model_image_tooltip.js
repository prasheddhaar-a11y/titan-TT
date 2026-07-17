// Shared global wiring for the ".model-hover-trigger" / ".model-image-tooltip"
// widget (plating-stock-number hover preview + Info/Close buttons).
// Extracted from inputscreening_picktable.js ("Original inline block #6") so
// every PickTable/RejectTable across every module gets working hover, click-
// to-pin, Close button, ESC, and click-outside-to-close behavior without
// duplicating this logic per template. Purely additive: only touches
// elements carrying these classes, which templates already render.
document.addEventListener("DOMContentLoaded", function () {
  let openTooltip = null;

  function closeTooltip(tooltip, trigger) {
    if (tooltip) {
      tooltip.classList.remove("pinned");
      tooltip.style.opacity = "0";
      tooltip.style.pointerEvents = "none";
      tooltip.style.visibility = "hidden";
      tooltip.style.display = "none";
      const infoBtn = tooltip.querySelector(".info-btn");
      const closeBtn = tooltip.querySelector(".close-btn");
      if (infoBtn) infoBtn.style.display = "none";
      if (closeBtn) closeBtn.style.display = "none";
      if (trigger) {
        trigger.style.backgroundColor = "";
        trigger.style.borderRadius = "";
      }
      openTooltip = null;
    }
  }

  document
    .querySelectorAll(".model-image-tooltip .info-btn")
    .forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        const row = btn.closest("tr");
        let lotId = null;
        let batchId = null;
        if (row) {
          batchId = row.getAttribute("data-batch-id");
        }
        let url = "/adminportal/dp_visualaid/";
        if (lotId) {
          url += encodeURIComponent(lotId) + "/";
        }
        if (batchId) {
          url += "?batch_id=" + encodeURIComponent(batchId);
        }
        window.location.href = url;
      });
    });

  document.querySelectorAll(".model-hover-trigger").forEach(function (trigger) {
    const tooltip = trigger.querySelector(".model-image-tooltip");
    trigger.addEventListener("mouseenter", function () {
      if (tooltip && !tooltip.classList.contains("pinned")) {
        tooltip.style.display = "flex";
        tooltip.style.visibility = "visible";
        tooltip.style.opacity = "1";
        tooltip.style.pointerEvents = "auto";
        const infoBtn = tooltip.querySelector(".info-btn");
        const closeBtn = tooltip.querySelector(".close-btn");
        if (infoBtn) infoBtn.style.display = "block";
        if (closeBtn) closeBtn.style.display = "block";
      }
    });
    trigger.addEventListener("mouseleave", function () {
      if (tooltip && !tooltip.classList.contains("pinned")) {
        tooltip.style.opacity = "0";
        tooltip.style.pointerEvents = "none";
        const infoBtn = tooltip.querySelector(".info-btn");
        const closeBtn = tooltip.querySelector(".close-btn");
        if (infoBtn) infoBtn.style.display = "none";
        if (closeBtn) closeBtn.style.display = "none";
      }
    });
    if (tooltip) {
      tooltip.addEventListener("mouseenter", function () {
        if (!tooltip.classList.contains("pinned")) {
          tooltip.style.display = "flex";
          tooltip.style.visibility = "visible";
        }
        tooltip.style.opacity = "1";
        tooltip.style.pointerEvents = "auto";
        const infoBtn = tooltip.querySelector(".info-btn");
        const closeBtn = tooltip.querySelector(".close-btn");
        if (infoBtn) infoBtn.style.display = "block";
        if (closeBtn) closeBtn.style.display = "block";
      });
      tooltip.addEventListener("mouseleave", function () {
        if (!tooltip.classList.contains("pinned")) {
          tooltip.style.opacity = "0";
          tooltip.style.pointerEvents = "none";
          const infoBtn = tooltip.querySelector(".info-btn");
          const closeBtn = tooltip.querySelector(".close-btn");
          if (infoBtn) infoBtn.style.display = "none";
          if (closeBtn) closeBtn.style.display = "none";
        }
      });
    }
    trigger.addEventListener("click", function (e) {
      e.stopPropagation();
      if (tooltip) {
        if (openTooltip && openTooltip !== tooltip) {
          const prevTrigger = openTooltip.closest(".model-hover-trigger");
          closeTooltip(openTooltip, prevTrigger);
        }
        tooltip.classList.add("pinned");
        tooltip.style.display = "flex";
        tooltip.style.visibility = "visible";
        tooltip.style.opacity = "1";
        tooltip.style.pointerEvents = "auto";
        openTooltip = tooltip;
        const infoBtn = tooltip.querySelector(".info-btn");
        const closeBtn = tooltip.querySelector(".close-btn");
        if (infoBtn) infoBtn.style.display = "block";
        if (closeBtn) closeBtn.style.display = "block";
        trigger.style.backgroundColor = "#e3f2fd";
        trigger.style.borderRadius = "4px";
      }
    });
    const closeBtn = tooltip ? tooltip.querySelector(".close-btn") : null;
    if (closeBtn) {
      closeBtn.style.display = "none";
      closeBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        closeTooltip(tooltip, trigger);
        closeBtn.style.transform = "scale(0.9)";
        setTimeout(function () {
          if (closeBtn.style) {
            closeBtn.style.transform = "scale(1)";
          }
        }, 150);
      });
      closeBtn.addEventListener("mouseenter", function () {
        closeBtn.style.backgroundColor = "#c82333";
        closeBtn.style.transform = "scale(1.05)";
      });
      closeBtn.addEventListener("mouseleave", function () {
        closeBtn.style.backgroundColor = "#dc3545";
        closeBtn.style.transform = "scale(1)";
      });
    }
  });

  document.addEventListener("click", function (e) {
    if (
      openTooltip &&
      !e.target.closest(".model-image-tooltip") &&
      !e.target.closest(".model-hover-trigger")
    ) {
      const openTrigger = openTooltip.closest(".model-hover-trigger");
      closeTooltip(openTooltip, openTrigger);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && openTooltip) {
      const openTrigger = openTooltip.closest(".model-hover-trigger");
      closeTooltip(openTooltip, openTrigger);
    }
  });

  document.querySelectorAll(".model-image-tooltip").forEach(function (tooltip) {
    tooltip.addEventListener("click", function (e) {
      e.stopPropagation();
    });
  });
});
