def sort_images_front_first(images):
    """Return images with front-view entries first, preserving a stable fallback order."""
    def image_key(image):
        parts = []
        for attr in ("image_type", "view_type", "angle", "label", "name"):
            value = getattr(image, attr, "")
            if value:
                parts.append(str(value).lower())

        master_image = getattr(image, "master_image", None)
        if master_image:
            parts.append(str(getattr(master_image, "name", master_image)).lower())

        text = " ".join(parts)
        front_rank = 0 if "front" in text else 1
        return front_rank, text

    return sorted(images or [], key=image_key)