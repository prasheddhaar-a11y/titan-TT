"""
Shared helper for resolving which ModelImage should be treated as a
model's "Front View" when a view/template needs a single representative
image (e.g. the plating-stock-number hover preview).

ModelImage records are tagged only by filename convention
(<model_no>xx<bath_code><version><VIEW_SUFFIX>.ext, e.g. "1805xxd02FV.jpg").
The M2M ModelMaster.images has no ordering guarantee, so naively taking
images.all()[0] can surface a Top View / Isometric View / Side View instead
of the Front View. This module centralizes the view-code detection so every
module reuses the same rule instead of re-implementing "first image wins".
"""

# Front View wins; Front-Side View is the closest available substitute when
# a model has no dedicated FV upload yet.
_FRONT_VIEW_PREFERENCE = ('FV', 'FSV')

_VIEW_SUFFIXES = ('RSV', 'LSV', 'FSV', 'TV', 'FV', 'IV', 'BV')


def detect_image_view(name):
    """Return the view-code suffix (e.g. 'FV') found in an image filename, or None."""
    import os
    base_name = os.path.splitext(os.path.basename(name or ''))[0].upper()
    for suffix in _VIEW_SUFFIXES:
        if base_name.endswith(suffix) or base_name.endswith('_' + suffix):
            return suffix
    return None


def sort_images_front_first(images):
    """
    Reorder an iterable of ModelImage objects so the Front View (or the
    closest available substitute) comes first. All images are kept and
    their relative order among themselves is otherwise preserved -
    this only moves the front-view candidate to the front.
    """
    images = list(images)

    for view_code in _FRONT_VIEW_PREFERENCE:
        for img in images:
            master_image = getattr(img, 'master_image', None)
            lookup_name = getattr(img, 'original_filename', '') or getattr(master_image, 'name', '') or ''
            if detect_image_view(lookup_name) == view_code:
                return [img] + [other for other in images if other is not img]

    return images
