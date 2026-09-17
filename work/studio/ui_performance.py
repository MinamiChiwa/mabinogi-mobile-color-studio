"""Input policy for settings controls.

Use CTk's synchronous size drawing. Per-widget delayed drawing leaves the
native geometry and canvas contents on different frames during window drags.
"""
from customtkinter import CTkSlider

class DeliberateSlider(CTkSlider):
    """Adjust by click/drag only."""
    def _mouse_scroll_event(self,event):
        return None
