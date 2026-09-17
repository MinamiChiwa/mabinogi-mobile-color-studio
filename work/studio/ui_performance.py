"""Coalesce resize bursts without changing Tk geometry or DPI calculations."""
from customtkinter.windows.widgets.core_widget_classes import CTkBaseClass

def install_resize_coalescing():
    if getattr(CTkBaseClass,'_studio_resize_installed',False):return
    original_destroy=CTkBaseClass.destroy
    def resized(self,event):
        width=self._reverse_widget_scaling(event.width)
        height=self._reverse_widget_scaling(event.height)
        if round(self._current_width)==round(width) and round(self._current_height)==round(height):return
        self._current_width=width;self._current_height=height
        if getattr(self,'_studio_resize_job',None) is None:
            def draw():
                self._studio_resize_job=None
                self._draw(no_color_updates=True)
            self._studio_resize_job=self.after(16,draw)
    def destroy(self):
        job=getattr(self,'_studio_resize_job',None)
        if job is not None:
            self.after_cancel(job);self._studio_resize_job=None
        original_destroy(self)
    CTkBaseClass._update_dimensions_event=resized
    CTkBaseClass.destroy=destroy
    CTkBaseClass._studio_resize_installed=True
