"""Responsive Tk geometry regressions; no game reads or input."""
import sys
import types
import unittest

import app
import test_native_ui_hit_testing as hit_testing


@unittest.skipUnless(sys.platform == 'win32', 'Native Tk geometry requires Windows')
class ResponsiveGeometryTests(unittest.TestCase):
    def setUp(self):
        helper = hit_testing.NativeUIHitTestingTests()
        self.addCleanup(helper.doCleanups)
        helper.setUp()
        self.helper = helper
        self.ui = helper.ui
        app.ct.set_widget_scaling(1.)
        app.ct.set_window_scaling(1.)
        helper.pump(.15)

    def test_fixed_content_window_scales_when_widget_density_changes(self):
        # A separate real scroll frame isolates its scaling contract from the
        # main window's incidental Configure/reflow callbacks.
        frame = app.FixedContentScrollableFrame(
            self.ui, width=759, height=402, corner_radius=0)
        frame.set_fixed_content_width(759, 776)
        initial_width = float(frame._parent_canvas.itemcget(
            frame._create_window_id, 'width'))

        app.ct.set_widget_scaling(.7)
        self.helper.pump(.15)

        scaled_width = float(frame._parent_canvas.itemcget(
            frame._create_window_id, 'width'))
        self.assertAlmostEqual(
            scaled_width, initial_width * .7, delta=1.,
            msg='Embedded content retained its old native width after scaling')
        self.assertEqual(self.helper.errors, [])

    def test_scroll_viewport_requests_no_more_than_available_window_width(self):
        self.ui.geometry('800x850+20+20')
        self.helper.pump(.2)
        outer = self.ui.body_scroll._parent_frame
        padding = int(outer.grid_info()['padx']) * 2

        # Tk can constrain an oversized request to the grid cell. Assert the
        # requested geometry too, so fitting does not depend on that clipping.
        requested_total = outer.winfo_reqwidth() + padding
        self.assertLessEqual(
            requested_total, self.ui.page.winfo_width(),
            f'Viewport plus side padding requests {requested_total} pixels '
            f'inside a {self.ui.page.winfo_width()} pixel page')
        self.assertEqual(self.helper.errors, [])

    def test_same_breakpoint_resize_keeps_card_dimensions_and_centers_content(self):
        for density in (1., .7):
            with self.subTest(density=density):
                app.ct.set_widget_scaling(density)
                self.ui.geometry(f'{round(1120*density)}x850+20+20')
                self.helper.pump(.15)
                initial_widths=[card.winfo_width() for card in self.ui.cards]
                self.assertTrue(all(abs(width-app.CARD_WIDTH*density)<=1
                                    for width in initial_widths), initial_widths)
                for logical_width in (1240, 1380):
                    self.ui.geometry(f'{round(logical_width*density)}x850+20+20')
                    self.helper.pump(.08)
                    self.assertEqual(self.ui._layout_columns,3)
                    self.assertEqual([card.winfo_width() for card in self.ui.cards],
                                     initial_widths)
                    canvas=self.ui.body_scroll._parent_canvas
                    bounds=canvas.bbox(self.ui.body_scroll._create_window_id)
                    self.assertEqual(self.ui.body_scroll.winfo_manager(),'canvas')
                    content_width=bounds[2]-bounds[0]
                    self.assertAlmostEqual(bounds[0],
                                           (canvas.winfo_width()-content_width)/2,
                                           delta=1.)
        self.assertEqual(self.helper.errors, [])

    def test_one_two_and_three_column_layouts_keep_standard_card_width(self):
        for density in (1., .7):
            app.ct.set_widget_scaling(density)
            for logical_width,columns in ((560,1),(850,2),(1200,3)):
                with self.subTest(density=density,columns=columns):
                    self.ui.geometry(f'{round(logical_width*density)}x850+20+20')
                    self.helper.pump(.12)
                    self.assertEqual(self.ui._layout_columns,columns)
                    for card in self.ui.cards:
                        self.assertAlmostEqual(card.winfo_width(),
                                               app.CARD_WIDTH*density,delta=1.)
                    if columns==2:
                        third=self.ui.cards[2]
                        self.assertAlmostEqual(third.winfo_x()+third.winfo_width()/2,
                                               self.ui.card_body.winfo_width()/2,
                                               delta=1.)
        self.assertEqual(self.helper.errors, [])

    def test_long_status_text_wraps_to_narrow_window_width(self):
        self.ui.geometry('420x950+20+20')
        self.helper.pump(.15)
        text='Long diagnostic text describing the next refinement and the best measured combination retained at the deadline. ' * 2
        self.ui.status.configure(text=text)
        self.ui.set_detail(text)
        self.helper.pump(.08)
        for label in (self.ui.status,self.ui.detail,self.ui.footer):
            self.assertLessEqual(label._label.winfo_reqwidth(),label.winfo_width()+2,
                                 'Text wrapped beyond the actual visible label width')
        self.assertEqual(self.helper.errors, [])


class ResizeDebounceTests(unittest.TestCase):
    def test_return_to_settled_width_discards_pending_narrow_layout(self):
        scheduled = {}
        applied_widths = []

        def schedule(delay, callback):
            scheduled['layout'] = callback
            return 'layout'

        window = types.SimpleNamespace(
            page=types.SimpleNamespace(_get_widget_scaling=lambda: 1.),
            winfo_width=lambda: 800,
            _layout_width=800,
            _pending_layout_width=None,
            _resize_layout_job=None,
            after=schedule,
            after_cancel=lambda job: scheduled.pop(job, None),
            reflow=applied_widths.append,
        )
        window._run_scheduled_reflow = lambda: app.App._run_scheduled_reflow(window)

        app.App.schedule_layout(window, types.SimpleNamespace(widget=window, width=700))
        app.App.schedule_layout(window, types.SimpleNamespace(widget=window, width=800))
        for callback in list(scheduled.values()):
            callback()

        self.assertNotIn(
            700, applied_widths,
            'A pending narrow layout ran after the window returned to 800 pixels')


if __name__ == '__main__':
    unittest.main()
