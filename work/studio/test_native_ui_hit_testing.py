"""Real Windows Tk hit regions after native completion; no game reads or input."""
import sys
import tempfile
import threading
import time
import types
import unittest
import weakref
from pathlib import Path
from unittest.mock import patch

import app
from search_overlay import SearchOverlay


RULES=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
RESULT=dict(stop_reason='insufficient_time',verified=True,accepted=False,
            target_exact=False,actual_colors=['#9ACDD9','#8BA1AB','#719D68'],
            actual_deltas=[80.,65.,55.],maximum=80.,average=66.67,
            outcome='compromise',restored=False,best_actual_colors=['#BF67AB','#C06851','#E588AD'])


@unittest.skipUnless(sys.platform=='win32','Native Tk hit testing requires Windows')
class NativeUIHitTestingTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.original_scaling=(app.ct.ScalingTracker.widget_scaling,app.ct.ScalingTracker.window_scaling)
        for replacement in (patch.object(app,'DATA',Path(self.folder.name)),
                            patch.object(app.App,'hotkey_loop'),
                            patch.object(app.i18n,'_widgets',weakref.WeakSet()),
                            patch.object(app.i18n,'_refreshers',weakref.WeakKeyDictionary()),
                            patch.object(app,'resolve_target',side_effect=RuntimeError('Isolated UI test'))):
            replacement.start();self.addCleanup(replacement.stop)
        self.ui=app.App()
        self.addCleanup(self.close_ui)
        # Keep this fixture visible while desktop tools render progress. The
        # overlay is created later, so its topmost surface still intercepts
        # main-window hit regions until native completion withdraws it.
        self.ui.attributes('-topmost',True)
        self.errors=[]
        self.ui.report_callback_exception=lambda *exc:self.errors.append(str(exc[1]))
        self.pump(.2)

    def close_ui(self):
        self.ui._hotkeys_stop.set()
        self.ui._resize_redraw.restore()
        for job in self.ui.tk.call('after','info'):
            self.ui.tk.call('after','cancel',job)
        self.ui.destroy()
        # Restore global test density only after this hierarchy is gone. Doing
        # it before destroy exposed a half-scaled window during fixture cleanup.
        app.ct.set_widget_scaling(self.original_scaling[0])
        app.ct.set_window_scaling(self.original_scaling[1])
        app.ct.ScalingTracker.update_loop_running=False

    def pump(self,seconds=.15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.ui.update();time.sleep(.005)

    def hit(self,widget):
        x=widget.winfo_rootx()+widget.winfo_width()//2
        y=widget.winfo_rooty()+widget.winfo_height()//2
        hit=self.ui.winfo_containing(x,y)
        ancestor=hit
        while ancestor is not None and ancestor is not widget:
            ancestor=getattr(ancestor,'master',None)
        diagnostic=dict(point=(x,y),widget_rect=(widget.winfo_rootx(),widget.winfo_rooty(),widget.winfo_width(),widget.winfo_height()),
                        main_geometry=self.ui.winfo_geometry(),main_state=self.ui.state(),main_viewable=self.ui.winfo_viewable(),
                        screen=(self.ui.winfo_screenwidth(),self.ui.winfo_screenheight()),
                        scaling=(self.ui._get_window_scaling(),self.ui.page._get_widget_scaling()),
                        overlay_state=self.ui.overlay.state() if self.ui.overlay is not None else None)
        self.assertIs(ancestor,widget,f'{widget} center is intercepted by {hit}; {diagnostic}')
        return hit,x,y

    def click(self,widget):
        hit,x,y=self.hit(widget)
        hit.event_generate('<Enter>',x=x-hit.winfo_rootx(),y=y-hit.winfo_rooty())
        hit.event_generate('<Button-1>',x=x-hit.winfo_rootx(),y=y-hit.winfo_rooty())
        hit.event_generate('<ButtonRelease-1>',x=x-hit.winfo_rootx(),y=y-hit.winfo_rooty())
        self.pump(.03)

    def begin(self):
        self.ui.active_rules=RULES
        self.ui.busy=True
        self.ui.runner=types.SimpleNamespace(stop=threading.Event())
        self.ui.start.configure(state='disabled')
        if self.ui.overlay is None:
            self.ui.overlay=SearchOverlay(self.ui,self.ui.stop,settings_path=Path(self.folder.name)/'settings.json')
        self.ui.overlay.begin(RULES)
        # Position the real topmost surface over the first card, as in rc10.
        self.ui.overlay.geometry(f'+{self.ui.cards[0].target_entry.winfo_rootx()}+{self.ui.cards[0].swatch.winfo_rooty()-30}')
        self.pump()

    def test_native_finished_releases_main_hit_regions_and_next_run_reopens_overlay(self):
        for scaling in (1.,1.5):
            with self.subTest(scaling=scaling):
                app.ct.set_widget_scaling(scaling)
                app.ct.set_window_scaling(scaling)
                self.ui.geometry('1120x850+20+20');self.pump()
                self.begin()
                self.ui.q.put(('native_result',RESULT));self.ui.q.put(('finished',{}))
                self.pump()
                # These centers were intercepted by the terminal result overlay.
                for widget in (self.ui.toolbar_buttons[0],self.ui.start,self.ui.stop_button,
                               self.ui.cards[0].target_entry,self.ui.cards[0].swatch,
                               self.ui.cards[0].mode_selector,self.ui.cards[0].enable_switch):
                    self.hit(widget)
                self.assertFalse(self.ui.busy)
                self.assertIsNone(self.ui.runner)
                self.assertIsNone(self.ui.grab_current())
                self.assertEqual(self.ui.start.cget('state'),'normal')
                self.assertEqual(self.ui.history[0]['regions'][0]['color'],'#9ACDD9')
                with patch.object(app.colorchooser,'askcolor',return_value=((1,2,3),'#010203')):
                    self.click(self.ui.cards[0].swatch)
                self.assertEqual(self.ui.cards[0].target.get(),'#010203')
                old_enabled=self.ui.cards[0].enabled.get()
                self.click(self.ui.cards[0].enable_switch)
                self.assertEqual(self.ui.cards[0].enabled.get(),not old_enabled)
                self.click(self.ui.toolbar_buttons[0])
                self.assertTrue((Path(self.folder.name)/'profile.json').exists())
                # Saving opens the preset editor; close it before the next
                # native run so its top-level cannot intercept main-window
                # hit regions during the scaling subcase.
                preset_dialog=self.ui._dialogs.get('presets')
                if preset_dialog is not None and preset_dialog.winfo_exists():
                    preset_dialog.destroy()
                    self.pump(.05)
                self.begin()
                self.assertEqual(self.ui.overlay.state(),'normal')
                self.assertFalse(self.ui.overlay._dismissed)
                # A later atlas run retains its visible terminal result surface.
                self.ui.overlay.phase='verified'
                self.ui.overlay.handle('finished',{})
                self.assertEqual(self.ui.overlay.state(),'normal')
                self.ui.overlay.dismiss()
        self.assertEqual(self.errors,[])

    def test_native_failure_finished_also_releases_overlay(self):
        self.begin()
        self.ui.overlay.handle('native_progress',{'stage':'native_validate','message':'Checking data'})
        self.ui.overlay.handle('finished',{})
        self.hit(self.ui.cards[0].target_entry)
        self.assertEqual(self.ui.overlay.state(),'withdrawn')
        self.assertIsNone(self.ui.grab_current())


if __name__=='__main__':unittest.main()
