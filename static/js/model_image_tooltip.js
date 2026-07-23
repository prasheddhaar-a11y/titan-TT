(function () {
  var openTooltip = null;
  var visualAidCache = Object.create(null);

  function closestTrigger(node) {
    return node && node.closest ? node.closest(".model-hover-trigger") : null;
  }

  function getTooltip(trigger) {
    return trigger ? trigger.querySelector(".model-image-tooltip") : null;
  }

  function containsEither(trigger, tooltip, node) {
    return !!(
      node &&
      ((trigger && trigger.contains(node)) || (tooltip && tooltip.contains(node)))
    );
  }

  function setButtonsVisible(tooltip, visible) {
    if (!tooltip) return;
    tooltip.querySelectorAll(".info-btn, .close-btn").forEach(function (btn) {
      btn.style.display = visible ? "block" : "none";
    });
  }

  function getStockNo(trigger) {
    if (!trigger) return "";
    return (
      trigger.getAttribute("data-plating-stk-no") ||
      trigger.getAttribute("data-model-no") ||
      (trigger.textContent || "").trim()
    );
  }

  function getVisualAidUrl(stockNo) {
    return "/adminportal/dp_visualaid/?plating_stk_no=" + encodeURIComponent(stockNo || "");
  }

  function getApiUrl(stockNo) {
    return "/api/visual-aid/" + encodeURIComponent(stockNo || "") + "/";
  }

  function updateTooltipImage(tooltip, url) {
    if (!tooltip || !url) return;
    var gallery = tooltip.querySelector(".img-gallery");
    if (!gallery) return;
    if (tooltip.getAttribute("data-hover-preview") === "iv-only") {
      gallery.innerHTML = "";
    }
    var img = gallery.querySelector("img");
    if (!img) {
      img = document.createElement("img");
      img.style.width = "55px";
      img.style.height = "55px";
      img.style.objectFit = "cover";
      img.style.borderRadius = "6px";
      gallery.innerHTML = "";
      gallery.appendChild(img);
    }
    img.src = url;
  }

  function loadVisualAid(trigger, tooltip) {
    var stockNo = getStockNo(trigger);
    if (!stockNo) return;

    var infoBtn = tooltip ? tooltip.querySelector(".info-btn") : null;
    if (infoBtn && !infoBtn.dataset.infoUrl) infoBtn.dataset.infoUrl = getVisualAidUrl(stockNo);

    if (visualAidCache[stockNo]) {
      updateTooltipImage(tooltip, visualAidCache[stockNo].iv_image || visualAidCache[stockNo].hover_image);
      return;
    }

    fetch(getApiUrl(stockNo), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (response) {
        if (!response.ok) throw new Error("Visual Aid API failed");
        return response.json();
      })
      .then(function (data) {
        visualAidCache[stockNo] = data;
        updateTooltipImage(tooltip, data.iv_image || data.hover_image);
      })
      .catch(function () {
        // Keep the server-rendered fallback image if the API is unavailable.
      });
  }

  function showTooltip(trigger) {
    var tooltip = getTooltip(trigger);
    if (!tooltip) return;

    if (openTooltip && openTooltip !== tooltip) {
      closeTooltip(openTooltip);
    }

    tooltip.style.display = "flex";
    tooltip.style.visibility = "visible";
    tooltip.style.opacity = "1";
    tooltip.style.pointerEvents = "auto";
    tooltip.style.zIndex = "500000";
    setButtonsVisible(tooltip, true);
    openTooltip = tooltip;
    loadVisualAid(trigger, tooltip);
  }

  function closeTooltip(tooltip) {
    if (!tooltip) return;
    tooltip.classList.remove("pinned");
    tooltip.style.opacity = "0";
    tooltip.style.pointerEvents = "none";
    tooltip.style.visibility = "hidden";
    tooltip.style.display = "none";
    setButtonsVisible(tooltip, false);
    if (openTooltip === tooltip) openTooltip = null;
  }

  document.addEventListener("mouseover", function (event) {
    var trigger = closestTrigger(event.target);
    if (!trigger) return;

    var tooltip = getTooltip(trigger);
    if (containsEither(trigger, tooltip, event.relatedTarget)) return;
    showTooltip(trigger);
  });

  document.addEventListener("mouseout", function (event) {
    var trigger = closestTrigger(event.target);
    if (!trigger) return;

    var tooltip = getTooltip(trigger);
    if (containsEither(trigger, tooltip, event.relatedTarget)) return;
    if (tooltip && tooltip.classList.contains("pinned")) return;
    closeTooltip(tooltip);
  });

  document.addEventListener("click", function (event) {
    var infoBtn = event.target.closest(".model-image-tooltip .info-btn");
    if (infoBtn) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      var trigger = closestTrigger(infoBtn);
      var stockNo = getStockNo(trigger);
      window.location.href = infoBtn.dataset.infoUrl || getVisualAidUrl(stockNo);
      return;
    }

    var closeBtn = event.target.closest(".model-image-tooltip .close-btn");
    if (closeBtn) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      closeTooltip(closeBtn.closest(".model-image-tooltip"));
      return;
    }

    var trigger = closestTrigger(event.target);
    if (trigger) {
      event.stopPropagation();
      var tooltip = getTooltip(trigger);
      if (!tooltip) return;
      tooltip.classList.add("pinned");
      showTooltip(trigger);
      return;
    }

    if (openTooltip && !event.target.closest(".model-image-tooltip")) {
      closeTooltip(openTooltip);
    }
  }, true);

  document.addEventListener("mousedown", function (event) {
    var infoBtn = event.target.closest(".model-image-tooltip .info-btn");
    if (!infoBtn) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    var trigger = closestTrigger(infoBtn);
    var stockNo = getStockNo(trigger);
    window.location.href = infoBtn.dataset.infoUrl || getVisualAidUrl(stockNo);
  }, true);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && openTooltip) closeTooltip(openTooltip);
  });
})();
