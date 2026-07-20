"""
Backend-owned color assignment for Model Presents circles.

Golden rule: colors are assigned once per Plating Stk No and persisted in
ModelMaster.plating_color_code. Frontend and views must never invent colors
client-side or per-request; they only read what this service resolves.
"""
import logging

from django.db import transaction

from modelmasterapp.models import ModelMaster

logger = logging.getLogger(__name__)

# Curated, visually distinct palette. Cycled in order; extended deterministically
# below once exhausted so every Plating Stk No still gets a stable color.
COLOR_PALETTE = [
    "#e74c3c", "#f1c40f", "#2ecc71", "#3498db", "#9b59b6",
    "#e67e22", "#1abc9c", "#34495e", "#f39c12", "#d35400",
    "#c0392b", "#8e44ad", "#2980b9", "#27ae60", "#16a085",
    "#ff6b6b", "#4ecdc4", "#45b7d1", "#96ceb4", "#ffeaa7",
    "#dda0dd", "#98d8c8", "#f7dc6f", "#bb8fce", "#85c1e9",
]

DEFAULT_COLOR = "#cccccc"


def _next_color(used_colors):
    """Return the first palette color not already in use; fall back to a
    deterministic HSL color once the curated palette is exhausted."""
    for color in COLOR_PALETTE:
        if color not in used_colors:
            return color

    index = len(used_colors) - len(COLOR_PALETTE)
    hue = (index * 137) % 360  # golden-angle spacing keeps generated hues distinct
    return f"hsl({hue}, 65%, 50%)"


def get_or_assign_plating_color(plating_stk_no):
    """
    Return the DB-persisted color for a Plating Stk No, assigning and saving
    one (unique among all currently assigned colors) if it doesn't exist yet.

    Safe to call concurrently: assignment runs inside a row-locked transaction.
    """
    if not plating_stk_no:
        return DEFAULT_COLOR

    with transaction.atomic():
        rows = list(
            ModelMaster.objects.select_for_update()
            .filter(plating_stk_no=plating_stk_no)
            .only("id", "plating_color_code")
        )
        if not rows:
            return DEFAULT_COLOR

        existing = next((r.plating_color_code for r in rows if r.plating_color_code), None)
        if existing:
            return existing

        used_colors = set(
            ModelMaster.objects.exclude(plating_color_code__isnull=True)
            .exclude(plating_color_code="")
            .values_list("plating_color_code", flat=True)
            .distinct()
        )
        color = _next_color(used_colors)

        ModelMaster.objects.filter(plating_stk_no=plating_stk_no).update(plating_color_code=color)
        logger.info("Assigned plating color %s to Plating Stk No %s", color, plating_stk_no)
        return color


def get_model_colors_by_model_no(identifiers):
    """
    Resolve {identifier: hex_color} for a list of display identifiers coming from
    Model Presents columns. Callers across the codebase pass either a bare
    model_no (e.g. '1805') or a full Plating Stk No (e.g. '1805WBK02') — both are
    matched here, PSN first since that's what most call sites actually pass.
    Colors are read from (and assigned into) ModelMaster.plating_color_code —
    never generated client-side or per-request.
    """
    result = {}
    if not identifiers:
        return result

    unique_ids = list({str(i) for i in identifiers if i})

    # order_by('id') keeps the identifier -> ModelMaster pick deterministic
    # across calls when one identifier matches multiple ModelMaster rows.
    from django.db.models import Q

    models_qs = ModelMaster.objects.filter(
        Q(plating_stk_no__in=unique_ids) | Q(model_no__in=unique_ids)
    ).only("id", "model_no", "plating_stk_no", "plating_color_code").order_by("id")

    by_psn = {}
    by_model_no = {}
    for mm in models_qs:
        if mm.plating_stk_no:
            by_psn.setdefault(mm.plating_stk_no, mm)
        if mm.model_no:
            by_model_no.setdefault(mm.model_no, mm)

    for identifier in identifiers:
        key = str(identifier)
        mm = by_psn.get(key) or by_model_no.get(key)
        if mm and mm.plating_stk_no:
            result[identifier] = get_or_assign_plating_color(mm.plating_stk_no)
        else:
            result[identifier] = DEFAULT_COLOR

    return result
