import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from ui_performance import DeliberateSlider

class ResizeTests(unittest.TestCase):
    def test_card_breakpoints_fit_fixed_cards_without_stretching_them(self):
        from app import CARD_GAP,CARD_WIDTH,BODY_SIDE_PADDING,SCROLLBAR_WIDTH,MIN_WINDOW_WIDTH,columns_for_width
        two_columns=2*(CARD_WIDTH+2*CARD_GAP)+2*BODY_SIDE_PADDING+SCROLLBAR_WIDTH
        three_columns=3*(CARD_WIDTH+2*CARD_GAP)+2*BODY_SIDE_PADDING+SCROLLBAR_WIDTH
        self.assertEqual(MIN_WINDOW_WIDTH,CARD_WIDTH+2*CARD_GAP+2*BODY_SIDE_PADDING+SCROLLBAR_WIDTH)
        self.assertEqual(columns_for_width(MIN_WINDOW_WIDTH),1)
        self.assertEqual(columns_for_width(two_columns-1),1)
        self.assertEqual(columns_for_width(two_columns),2)
        self.assertEqual(columns_for_width(three_columns-1),2)
        self.assertEqual(columns_for_width(three_columns),3)

    def test_existing_column_count_does_not_regrid_cards_on_resize(self):
        from app import App
        cards=[SimpleNamespace(grid_configure=MagicMock()) for _ in range(3)]
        body=SimpleNamespace(configure=MagicMock(),grid_columnconfigure=MagicMock())
        scroll=SimpleNamespace(configure=MagicMock(),set_fixed_content_width=MagicMock())
        window=SimpleNamespace(_layout_columns=2,page=SimpleNamespace(configure=MagicMock()),card_body=body,body_scroll=scroll,cards=cards,
                               _fixed_content_widgets=(),intro=SimpleNamespace(configure=MagicMock()),intro_labels=[])
        App.apply_card_layout(window,2)
        window.page.configure.assert_not_called()
        scroll.set_fixed_content_width.assert_not_called()
        body.grid_columnconfigure.assert_not_called()
        for card in cards:card.grid_configure.assert_not_called()

    def test_card_reordering_happens_only_when_column_count_changes_and_outer_page_stays_responsive(self):
        from app import App
        cards=[SimpleNamespace(grid_configure=MagicMock()) for _ in range(3)]
        body=SimpleNamespace(configure=MagicMock(),grid_columnconfigure=MagicMock())
        scroll=SimpleNamespace(configure=MagicMock(),set_fixed_content_width=MagicMock())
        window=SimpleNamespace(_layout_columns=3,page=SimpleNamespace(configure=MagicMock()),card_body=body,body_scroll=scroll,cards=cards,
                               _fixed_content_widgets=(),intro=SimpleNamespace(configure=MagicMock()),intro_labels=[])
        App.apply_card_layout(window,2)
        from app import CARD_GAP,CARD_WIDTH
        # The page fills the native window at every size. Only its centered,
        # fixed-width scroll content changes at a card breakpoint.
        window.page.configure.assert_not_called()
        scroll.set_fixed_content_width.assert_called_once_with(2*(CARD_WIDTH+2*CARD_GAP))
        self.assertEqual(body.grid_columnconfigure.call_count,3)
        self.assertEqual([card.grid_configure.call_args.kwargs for card in cards],[
            dict(row=0,column=0,columnspan=1,sticky=''),dict(row=0,column=1,columnspan=1,sticky=''),dict(row=1,column=0,columnspan=2,sticky='')])
        for index in range(3):
            args=body.grid_columnconfigure.call_args_list[index].args
            self.assertEqual(args[0],index)
            self.assertEqual(body.grid_columnconfigure.call_args_list[index].kwargs['weight'],0)
        for card in cards:card.grid_configure.reset_mock()
        App.apply_card_layout(window,2)
        for card in cards:card.grid_configure.assert_not_called()

    def test_scroll_content_width_changes_only_when_layout_changes(self):
        from app import FixedContentScrollableFrame
        frame=SimpleNamespace(configure=MagicMock(),_parent_canvas=SimpleNamespace(itemconfigure=MagicMock()),
                              _set_outer_viewport_size=MagicMock(),
                              _create_window_id='content-window',_apply_widget_scaling=lambda width:width*1.25)
        FixedContentScrollableFrame.set_fixed_content_width(frame,712)
        frame.configure.assert_called_once_with(width=712)
        frame._set_outer_viewport_size.assert_called_once_with(712)
        frame._parent_canvas.itemconfigure.assert_called_once_with('content-window',width=890)

    def test_scroll_outer_frame_is_fixed_and_does_not_propagate_inner_content_height(self):
        from app import FixedContentScrollableFrame,SCROLLBAR_WIDTH,SCROLL_VIEWPORT_HEIGHT
        outer=SimpleNamespace(configure=MagicMock(),grid_propagate=MagicMock())
        frame=SimpleNamespace(_parent_frame=outer,_desired_height=SCROLL_VIEWPORT_HEIGHT,
                              _studio_viewport_height=SCROLL_VIEWPORT_HEIGHT)
        FixedContentScrollableFrame._set_outer_viewport_size(frame,712)
        outer.configure.assert_called_once_with(width=712+SCROLLBAR_WIDTH,height=SCROLL_VIEWPORT_HEIGHT)
        outer.grid_propagate.assert_called_once_with(False)

    def test_scroll_viewport_height_stays_fixed_when_card_rows_change(self):
        from app import FixedContentScrollableFrame,SCROLL_VIEWPORT_HEIGHT
        outer=SimpleNamespace(configure=MagicMock(),grid_propagate=MagicMock())
        frame=SimpleNamespace(_parent_frame=outer,_desired_height=1236,
                              _studio_viewport_height=SCROLL_VIEWPORT_HEIGHT)
        FixedContentScrollableFrame._set_outer_viewport_size(frame,356)
        outer.configure.assert_called_once_with(width=356+17,height=SCROLL_VIEWPORT_HEIGHT)

    def test_narrow_controls_move_optional_checkbox_to_its_own_right_aligned_row(self):
        from app import App
        checkbox=SimpleNamespace(grid_configure=MagicMock())
        window=SimpleNamespace(_controls_compact=False,auto_check=checkbox)
        App.apply_control_layout(window,True)
        checkbox.grid_configure.assert_called_once_with(row=1,column=0,columnspan=3,sticky='e')
        App.apply_control_layout(window,False)
        self.assertEqual(checkbox.grid_configure.call_args.kwargs,
                         dict(row=0,column=2,columnspan=1,sticky='e'))

    def test_resize_handler_ignores_changes_inside_current_breakpoint(self):
        from app import App
        window=SimpleNamespace(winfo_width=lambda:900,page=SimpleNamespace(_get_widget_scaling=lambda:1),
                               _layout_columns=2,_topbars_compact=False,_controls_compact=False,reflow=MagicMock())
        App.schedule_layout(window,SimpleNamespace(widget=window,width=900))
        App.schedule_layout(window,SimpleNamespace(widget=window,width=850))
        window.reflow.assert_not_called()
        App.schedule_layout(window,SimpleNamespace(widget=window,width=735))
        window.reflow.assert_called_once_with(735)

    def test_wheel_never_changes_slider_or_invokes_callback(self):
        slider=SimpleNamespace(_update_value=MagicMock())
        for delta in (-120,120):
            DeliberateSlider._mouse_scroll_event(slider,SimpleNamespace(delta=delta,num=0))
        slider._update_value.assert_not_called()

    def test_initial_density_reserves_space_for_all_controls(self):
        from app import App,MIN_WINDOW_WIDTH,COMPACT_HEADER_EXTRA_HEIGHT
        for screen in ((1024,768),(1920,1080),(3840,2160),(5120,2880)):
            for dpi in (1,1.25,1.5,2,2.5):
                with self.subTest(screen=screen,dpi=dpi):
                    window=SimpleNamespace(_get_window_scaling=lambda:dpi,
                        winfo_screenwidth=lambda:screen[0],winfo_screenheight=lambda:screen[1],
                        minsize=MagicMock(),geometry=MagicMock(),update_idletasks=MagicMock(),
                        page=SimpleNamespace(winfo_reqheight=lambda:600))
                    with patch('app.ct.set_widget_scaling') as scaling:
                        App.fit_screen(window)
                    scaling.assert_called_once_with(window._ui_scale)
                    available_width=max(1,int(screen[0]/dpi)-80)
                    available_height=max(1,int(screen[1]/dpi)-100)
                    required_height=max(560,600+round(COMPACT_HEADER_EXTRA_HEIGHT*window._ui_scale))
                    self.assertEqual(window.minsize.call_args.args,
                                     (min(MIN_WINDOW_WIDTH,available_width),min(required_height,available_height)))
                    parts=window.geometry.call_args.args[0].split('+')
                    width,height=map(int,parts[0].split('x'))
                    self.assertLessEqual(width,available_width)
                    self.assertLessEqual(height,available_height)
                    self.assertLessEqual(width+20,screen[0]/dpi-60)
                    self.assertLessEqual(height+20,screen[1]/dpi-80)
                    self.assertGreaterEqual(window._ui_scale,.7)

    def test_scroll_viewport_fits_one_fixed_card_row_without_vertical_stretch(self):
        from app import CARD_HEIGHT,CARD_GAP,INTRO_HEIGHT,SCROLL_VIEWPORT_HEIGHT
        self.assertEqual(SCROLL_VIEWPORT_HEIGHT,INTRO_HEIGHT+10+CARD_HEIGHT+2*CARD_GAP)

    def test_resize_redraw_flags_are_removed_and_restored_without_overwriting_other_bits(self):
        from resize_rendering import TopLevelResizeRedrawOptimization,GCL_STYLE,CS_HREDRAW,CS_VREDRAW
        class User32:
            def __init__(self):self.style=CS_HREDRAW|CS_VREDRAW|0x1000
            def GetClassLongPtrW(self,hwnd,index):return self.style
            def SetClassLongPtrW(self,hwnd,index,value):
                old=self.style;self.style=value;return old
            def GetAncestor(self,hwnd,flag):return hwnd+1
        api=User32();optimization=TopLevelResizeRedrawOptimization(api,platform='win32')
        self.assertTrue(optimization.disable_for(10))
        self.assertEqual(api.style,0x1000)
        api.style|=0x2000
        self.assertTrue(optimization.restore())
        self.assertEqual(api.style,CS_HREDRAW|CS_VREDRAW|0x3000)

    def test_resize_redraw_optimization_is_noop_when_flags_are_absent_or_non_windows(self):
        from resize_rendering import TopLevelResizeRedrawOptimization
        api=SimpleNamespace(GetClassLongPtrW=lambda *_:0,SetClassLongPtrW=MagicMock())
        optimization=TopLevelResizeRedrawOptimization(api,platform='win32')
        self.assertFalse(optimization.disable_for(10))
        api.SetClassLongPtrW.assert_not_called()
        self.assertFalse(TopLevelResizeRedrawOptimization(api,platform='linux').disable_for(10))

    def test_overlay_reports_search_and_recovery_without_claiming_unverified_match(self):
        from search_overlay import SearchOverlay
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=False,tolerance=8)]+[dict(enabled=False)]*2
        overlay=SimpleNamespace(rules=rules,phase='waiting',render=MagicMock(),withdraw=MagicMock(),clear_candidates=MagicMock())
        SearchOverlay.handle(overlay,'scene',{'colors':['#FEFEFE',None,None]})
        self.assertEqual(overlay.phase,'searching')
        self.assertIn('已达标',overlay.render.call_args.args[0])
        SearchOverlay.handle(overlay,'scene',{'colors':[None,None,None]})
        self.assertNotIn('已达标',overlay.render.call_args.args[0])
        SearchOverlay.handle(overlay,'restoring',{})
        self.assertEqual(overlay.phase,'restoring')
        SearchOverlay.handle(overlay,'finished',{})
        overlay.withdraw.assert_called_once()
        overlay.clear_candidates.assert_called_once()

    def test_candidate_selection_rejects_expired_batch(self):
        from search_overlay import SearchOverlay
        button=MagicMock();callback=MagicMock()
        overlay=SimpleNamespace(batch_id='current',candidate_rows={0:button},select_candidate=callback,phase='choosing')
        SearchOverlay.choose(overlay,'expired',0)
        callback.assert_not_called()
        SearchOverlay.choose(overlay,'current',0)
        button.configure.assert_called_once_with(state='disabled')
        callback.assert_called_once_with('current',0)
        SearchOverlay.choose(overlay,'current',0)
        callback.assert_called_once_with('current',0)
