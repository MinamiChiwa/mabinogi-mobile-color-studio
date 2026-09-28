"""Map Tk overlay coordinates to physical screenshot pixels.

PIL captures use physical pixels while Tk event coordinates follow the
fullscreen window's current coordinate space. On a scaled display those
spaces may differ, so callers must map through the actual canvas dimensions.
"""


def image_point(event_x, event_y, canvas_size, image_size):
    """Return a bounded image pixel for a point in a display canvas."""
    canvas_width, canvas_height = (max(1, int(value)) for value in canvas_size)
    image_width, image_height = (max(1, int(value)) for value in image_size)
    x = int(float(event_x) * image_width / canvas_width)
    y = int(float(event_y) * image_height / canvas_height)
    return (max(0, min(image_width - 1, x)),
            max(0, min(image_height - 1, y)))


def screen_point(event_x, event_y, canvas_size, image_size, origin):
    """Map a canvas event to an absolute physical screen point."""
    x, y = image_point(event_x, event_y, canvas_size, image_size)
    return (int(origin[0]) + x, int(origin[1]) + y)
