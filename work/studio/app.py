import platform_win  # Set physical-pixel awareness before Tk or capture initializes.
import sys
if __name__=='__main__' and '--native-preflight' in sys.argv:
    from native_preflight import main as native_preflight_main
    raise SystemExit(native_preflight_main([arg for arg in sys.argv[1:] if arg!='--native-preflight']))
import customtkinter as ct
import tkinter as tk
from tkinter import colorchooser,messagebox
from pathlib import Path
import sys,json,threading,queue,ctypes,webbrowser
from app_data import resolve_data_directory
from engine import Runner
import i18n
from i18n import tr
from vision import normalize_hex
from palette import allowed_colors,overview
from palette_viewer import PaletteViewer
from search_overlay import SearchOverlay
from hotkeys import run_hotkeys
from window_picker import WindowPicker
from window_target import resolve_target
from atlas_service import AtlasService
from atlas_live_adapter import callbacks as atlas_callbacks
from result_history import describe_result,read_history,save_result
from eyedropper import pick_screen
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from vision import rgb
PALETTE_POOL=ThreadPoolExecutor(max_workers=1)
from PIL import Image,ImageDraw
from ui_performance import DeliberateSlider
from customtkinter.windows.widgets.scaling.scaling_base_class import CTkScalingBaseClass
from ui_dialogs import support_dialog,tutorial_dialog,GITHUB
from ui_settings import read_settings,save_settings
from profile_store import read_profile,write_profile,canonical_profile,PresetStore
from session_store import new_session_path,start_session_cleanup
from ui_typography import FONT_FAMILY,TITLE_FONT,SECTION_FONT,BODY_FONT,SMALL_FONT,ICON_FONT,HEX_FONT
from resize_rendering import TopLevelResizeRedrawOptimization
from resize_surface import NativeResizeSurface
from display_geometry import logical_size,work_area

from build_info import APP_VERSION
CARD_WIDTH=344
CARD_HEIGHT=372
CARD_GAP=6
BODY_SIDE_PADDING=12
SCROLLBAR_WIDTH=17
MIN_WINDOW_WIDTH=CARD_WIDTH+CARD_GAP*2+BODY_SIDE_PADDING*2+SCROLLBAR_WIDTH
COMPACT_HEADER_EXTRA_HEIGHT=80
# Show one complete card row and its note in the viewport. Keep this height
# fixed during native window resizing; extra cards remain vertically scrollable.
# The scroll viewport contains the 40-DIP intro and exactly one fixed card row.
# Keeping only that height prevents a large dead area beneath the cards.
INTRO_HEIGHT=72
SCROLL_VIEWPORT_HEIGHT=INTRO_HEIGHT+10+CARD_HEIGHT+2*CARD_GAP


def columns_for_width(width):
    """Select a card layout only when another fixed-size card fits."""
    usable=max(0,int(width)-BODY_SIDE_PADDING*2-SCROLLBAR_WIDTH)
    per_card=CARD_WIDTH+CARD_GAP*2
    return 3 if usable>=3*per_card else 2 if usable>=2*per_card else 1


class FixedContentScrollableFrame(ct.CTkScrollableFrame):
    """A viewport around fixed-size content.

    CTkScrollableFrame normally changes the embedded frame width for every
    canvas Configure event. That makes every child negotiate geometry while a
    native window is being dragged. The studio content owns its width, so the
    embedded frame must remain fixed and only the viewport may resize.
    """
    def __init__(self,*args,**kwargs):
        viewport_height=kwargs.get('height')
        super().__init__(*args,**kwargs)
        self._studio_viewport_height=viewport_height or self._desired_height
        # The inner frame grows when the user switches to one or two columns.
        # Stop that requested size from propagating back into the viewport.
        self._set_outer_viewport_size(self._desired_width)

    def _set_outer_viewport_size(self,width,viewport_width=None):
        # CTkScrollableFrame's grid_propagate wrapper ignores its arguments, so
        # size and lock the actual outer frame that holds the canvas/scrollbar.
        # The outer viewport follows the available window width.  Its embedded
        # canvas may remain wider than the viewport only when the minimum card
        # layout cannot fit, in which case horizontal clipping/scrolling is
        # preferable to forcing the native window wider than requested.
        outer_width=width if viewport_width is None else max(1,int(viewport_width))
        size=(outer_width+SCROLLBAR_WIDTH,self._studio_viewport_height)
        if size==getattr(self,'_studio_outer_size',None):return
        self._studio_outer_size=size
        self._parent_frame.configure(width=outer_width+SCROLLBAR_WIDTH,height=self._studio_viewport_height)
        self._parent_frame.grid_propagate(False)

    def _fit_frame_dimensions_to_canvas(self,event):
        # The inner frame is deliberately fixed-width. Vertical scrolling
        # still works because the canvas scrollregion is updated by the frame.
        # Its width is explicitly updated only when the card breakpoint changes.
        if self._orientation=='horizontal':
            super()._fit_frame_dimensions_to_canvas(event)
        else:self._center_content(event.width)

    def _center_content(self,viewport_width=None):
        if viewport_width is None:viewport_width=self._parent_canvas.winfo_width()
        content_width=self._apply_widget_scaling(self._desired_width)
        x=max(0,round((viewport_width-content_width)/2))
        self._parent_canvas.coords(self._create_window_id,x,0)

    def _set_scaling(self,new_widget_scaling,new_window_scaling):
        super()._set_scaling(new_widget_scaling,new_window_scaling)
        if self._orientation=='vertical':
            self._parent_canvas.itemconfigure(
                self._create_window_id,width=self._apply_widget_scaling(self._desired_width))

    def set_fixed_content_width(self,width,viewport_width=None):
        """Set the embedded content width at a layout breakpoint.

        The outer viewport has an independent width and may follow every
        resize event. Keeping this operation separate prevents all children
        from negotiating geometry while the native window is being dragged.
        """
        self.configure(width=width)
        self._set_outer_viewport_size(width,viewport_width)
        self._parent_canvas.itemconfigure(
            self._create_window_id,
            width=self._apply_widget_scaling(width),
        )
        self._center_content()

    def set_viewport_width(self,viewport_width):
        """Resize only the visible outer viewport, preserving inner content."""
        self._set_outer_viewport_size(self._desired_width,viewport_width)

def build_preview(target,tolerance):
    pixels=allowed_colors(target,tolerance)
    return pixels,overview(pixels)

def build_runner(emit,folder,strategy='native',entry=None,entry_size=None):
    # Native owns user-goal execution; existing visual strategies remain explicit.
    if strategy=='native':
        from native_live.service import run_native_search
        return Runner(emit,folder,native_runner=run_native_search)
    if strategy not in ('atlas','legacy'):raise ValueError('Unknown search strategy')
    service=AtlasService(atlas_callbacks(Path(folder)/'atlas_capture',strategy='grid'))
    return Runner(emit,folder,atlas_runner=service.run)

ct.set_appearance_mode('dark'); ct.set_default_color_theme('blue')
BG='#10151F'; PANEL='#192230'; INK='#EDF3FA'; MUTED='#94A4B8'; ACCENT='#62D7BD'
FONT=FONT_FAMILY
DATA=resolve_data_directory(
    (Path(sys.executable).resolve().parent if getattr(sys,'frozen',False)
     else Path(__file__).resolve().parent)/'data'
)
try:i18n.language=json.loads((DATA/'settings.json').read_text(encoding='utf-8')).get('language','简体中文')
except (OSError,ValueError):pass
i18n.install_widgets(ct)

class Card(ct.CTkFrame):
    def __init__(self,parent,index):
        super().__init__(parent,width=CARD_WIDTH,height=CARD_HEIGHT,fg_color=PANEL,corner_radius=18,border_width=1,border_color='#2A3546')
        self.index=index; self.enabled=tk.BooleanVar(value=True); self.mode=tk.StringVar(value='精准 HEX'); self.tolerance=tk.DoubleVar(value=8)
        self.target=tk.StringVar(value='#202020'); self.alt=tk.StringVar(value='')
        self.grid_columnconfigure(0,weight=1)
        heading=ct.CTkFrame(self,fg_color='transparent')
        heading.grid(row=0,column=0,padx=16,pady=(7,3),sticky='ew')
        ct.CTkLabel(heading,text=f'0{index+1}  /  颜色区域',font=SECTION_FONT,text_color=INK,height=22).pack(side='left')
        self.enable_switch=ct.CTkSwitch(heading,text='已启用' if self.enabled.get() else '未启用',width=95,variable=self.enabled,progress_color=ACCENT,font=SMALL_FONT)
        self.enable_switch.pack(side='right')
        self.priority=tk.IntVar(value=index+1)
        priority_bar=ct.CTkFrame(self,fg_color='transparent')
        priority_bar.grid(row=1,column=0,padx=16,pady=(0,2),sticky='ew')
        ct.CTkLabel(priority_bar,text='优先级',font=SMALL_FONT,text_color=MUTED,height=22).pack(side='left')
        self.priority_menu=ct.CTkOptionMenu(priority_bar,values=['1','2','3'],width=66,height=24,font=SMALL_FONT,
            command=lambda value:self.winfo_toplevel().set_card_priority(self.index,int(value)))
        self.priority_menu.set(str(index+1));self.priority_menu.pack(side='right')
        self.preview_frame=ct.CTkFrame(self,fg_color='transparent')
        self.preview_frame.grid(row=2,column=0,padx=16,pady=(4,3),sticky='ew')
        self.swatch=ct.CTkButton(self.preview_frame,text='点击选色',height=30,corner_radius=10,command=self.pick,font=BODY_FONT,fg_color='#202020',hover_color='#35445B')
        self.preview_frame.grid_columnconfigure(0,weight=1)
        self.preview_frame.grid_columnconfigure(1,weight=1)
        self.swatch.configure(width=110)
        self.swatch.grid(row=0,column=0,sticky='ew',padx=(0,4))
        ct.CTkButton(self.preview_frame,text='⌖  屏幕吸管',width=110,height=30,fg_color='#28364A',hover_color='#364D63',font=SMALL_FONT,command=lambda:pick_screen(self.winfo_toplevel(),self.target.set)).grid(row=0,column=1,sticky='ew',padx=(4,0))
        self.palette=ct.CTkLabel(self.preview_frame,text='',height=38)
        self.palette.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(3,0))
        self.palette.bind('<Button-1>',self.open_palette)
        self.palette.configure(cursor='hand2')
        self.palette_note=ct.CTkLabel(self.preview_frame,text='目标色集合',font=SMALL_FONT,text_color=MUTED,height=12,wraplength=260,anchor='w')
        self.palette_note.grid(row=2,column=0,columnspan=2,sticky='w')
        self._palette_future=None;self._palette_key=None;self._palette_pixels=None
        self._preview_job=None
        self.target_entry=ct.CTkEntry(self,textvariable=self.target,height=29,font=HEX_FONT,border_color='#36445B');self.target_entry.grid(row=3,column=0,padx=16,sticky='ew')
        self.label_alt=ct.CTkLabel(self,text='替代颜色 · 多个颜色用逗号分隔',font=SMALL_FONT,text_color=MUTED,height=15,wraplength=255,justify='left');self.label_alt.grid(row=4,column=0,padx=16,pady=(1,0),sticky='w')
        self.alt_entry=ct.CTkEntry(self,textvariable=self.alt,height=27,placeholder_text='#FFFFFF, #EAEAEA');self.alt_entry.grid(row=5,column=0,padx=16,sticky='ew')
        self.alts=ct.CTkFrame(self,fg_color='transparent',height=12); self.alts.grid(row=6,column=0,padx=16,pady=1,sticky='ew');self.alts.pack_propagate(False)
        self.mode_selector=ct.CTkSegmentedButton(self,values=[tr('精准 HEX'),tr('相似颜色')],command=self.select_mode,font=BODY_FONT,selected_color='#236D62',selected_hover_color='#2C8275',height=30)
        self.mode_selector.grid(row=7,column=0,padx=16,pady=(2,2),sticky='ew')
        i18n.on_language(self,self.refresh_language)
        self.slider=DeliberateSlider(self,from_=1,to=35,number_of_steps=34,variable=self.tolerance,command=self.change_mode,progress_color=ACCENT,button_color=ACCENT)
        self.slider.grid(row=8,column=0,padx=16,sticky='ew')
        self.hint=ct.CTkLabel(self,text='',font=SMALL_FONT,text_color=MUTED,height=19,wraplength=260,justify='left');self.hint.grid(row=9,column=0,padx=16,pady=(0,1),sticky='w')
        self.current=ct.CTkLabel(self,text='当前颜色  —',font=BODY_FONT,text_color=MUTED,height=17);self.current.grid(row=10,column=0,padx=16,pady=(0,1),sticky='w')
        self.best_label=ct.CTkLabel(self,text='最佳结果  —',font=SMALL_FONT,text_color=ACCENT,height=17,corner_radius=5);self.best_label.grid(row=11,column=0,padx=16,pady=(0,1),sticky='ew')
        self.target.trace_add('write',self.preview);self.alt.trace_add('write',self.preview); self.preview();self.change_mode()
        self.grid_propagate(False)
        self.enabled.trace_add('write',self.update_enabled)
        self.update_enabled()
    def update_enabled(self,*_):
        enabled=self.enabled.get()
        background='#192D35' if enabled else '#151B25'
        self.configure(fg_color=background,border_color=ACCENT if enabled else '#303A48',border_width=2 if enabled else 1)
        self.enable_switch.configure(text='已启用' if enabled else '未启用',text_color=ACCENT if enabled else MUTED)
        self.preview_frame.configure(fg_color=background)
        self.swatch.configure(text='点击选色' if enabled else '未启用')
    def select_mode(self,value):
        self.mode.set('精准 HEX' if value==tr('精准 HEX') else '相似颜色');self.change_mode()
    def refresh_language(self):
        self.mode_selector.configure(values=[tr('精准 HEX'),tr('相似颜色')])
        self.mode_selector.set(tr(self.mode.get()))
    def change_mode(self,*_):
        self.mode_selector.set(tr(self.mode.get()))
        exact=self.mode.get()=='精准 HEX'
        if getattr(self,'_last_exact',None)!=exact:
            self.slider.configure(state='disabled' if exact else 'normal',progress_color='#45505F' if exact else ACCENT,button_color='#596273' if exact else ACCENT,button_hover_color='#596273' if exact else '#80E5CF',fg_color='#303947' if exact else '#3A485D')
            self._last_exact=exact
        self.hint.configure(text='六位色码必须完全一致' if exact else f'目标色差 ΔE ≤ {self.tolerance.get():.0f} · 数值越小越接近目标')
        self.schedule_palette()
    def preview(self,*_):
        try:
            v=normalize_hex(self.target.get()); self.swatch.configure(fg_color=v,text_color='#17202B' if sum(int(v[i:i+2],16) for i in (1,3,5))>430 else 'white')
        except ValueError:pass
        for child in self.alts.winfo_children():child.destroy()
        for part in self.alt.get().replace('，',',').split(',')[:6]:
            try:ct.CTkLabel(self.alts,text='',width=20,height=18,corner_radius=4,fg_color=normalize_hex(part)).pack(side='left',padx=(0,5))
            except ValueError:pass
        if self.alts.winfo_children():self.alts.grid()
        else:self.alts.grid_remove()
        self.schedule_palette()
    def schedule_palette(self):
        if self._preview_job:self.after_cancel(self._preview_job)
        self._preview_job=self.after(80,self.draw_palette)
    def draw_palette(self):
        self._preview_job=None
        try:target=normalize_hex(self.target.get())
        except ValueError:
            self._palette_key=None
            self.palette.configure(image=None,text='请输入有效 HEX');self.palette_note.configure(text='颜色未设置完整');return
        exact=self.mode.get()=='精准 HEX'
        key=(target,0 if exact else float(self.tolerance.get()))
        if key==self._palette_key:return
        self._palette_key=key
        if self._palette_future:self._palette_future.cancel()
        if exact:
            self._palette_pixels=np.array([rgb(target)],np.uint8);self.render_palette();return
        # Keep the existing preview visible while its replacement is prepared.
        self.palette_note.configure(text='正在准备颜色预览…')
        future=PALETTE_POOL.submit(build_preview,*key);self._palette_future=future
        self.after(100,lambda:self.poll_palette(future,key))
    def poll_palette(self,future,key):
        if key!=self._palette_key or future is not self._palette_future:return
        if not future.done():self.after(100,lambda:self.poll_palette(future,key));return
        try:self._palette_pixels,im=future.result()
        except Exception:self.palette_note.configure(text='预览计算失败，请重新选择颜色');return
        self.render_palette(im)
    def render_palette(self,im=None):
        if im is None:im=overview(self._palette_pixels)
        self._display_key=self._palette_key
        new_image=ct.CTkImage(light_image=im,dark_image=im,size=(240,48))
        self.palette.configure(image=new_image,text='')
        self.palette_image=new_image
        count=len(self._palette_pixels)
        note=f'目标色集合 · {count:,} 色'
        note+=' · 点击查看全部'
        self.palette_note.configure(text=note)
    def open_palette(self,event=None):
        if self._palette_pixels is not None and getattr(self,'_display_key',None):
            PaletteViewer(self.winfo_toplevel(),self._palette_pixels,self._display_key[0],PALETTE_POOL)
    def pick(self):
        v=colorchooser.askcolor(parent=self,title=tr(f'区域 {self.index+1} · 选择目标颜色'))[1]
        if v:self.target.set(v.upper())
    def rule(self):
        if not self.enabled.get():return {'enabled':False,'colors':[],'exact':True,'tolerance':0}
        colors=[normalize_hex(self.target.get())]+[normalize_hex(x) for x in self.alt.get().replace('，',',').split(',') if x.strip()]
        return {'enabled':True,'colors':colors,'exact':self.mode.get()=='精准 HEX','tolerance':self.tolerance.get()}

class App(ct.CTk):
    def __init__(self):
        super().__init__();self.title(f"{tr('染色工坊 · 瑪奇 Mobile')}  v{APP_VERSION}");self.geometry('1120x800');self.minsize(MIN_WINDOW_WIDTH,560);self.configure(fg_color=BG)
        self._resize_redraw=TopLevelResizeRedrawOptimization()
        self.after(100,self.fit_screen)
        self.selected_window=None;self.overlay=None;self.active_rules=None;self.history=read_history(DATA/'history.json');self.best_summary=None
        self.q=queue.Queue();self.runner=None;self.busy=False;self.picking=False;self.keys={};self.cards=[]
        # The page follows the resizable native window. Its fixed-size card
        # viewport remains centered inside the responsive page.
        self.grid_columnconfigure(0,weight=1); self.grid_rowconfigure(0,weight=1)
        # The page follows the native window. Fixed-size card content is
        # centered inside it, while the top and bottom bars use the full width.
        initial_content_width=3*(CARD_WIDTH+2*CARD_GAP)
        self.page=ct.CTkFrame(self,fg_color='transparent')
        self.page.grid(row=0,column=0,sticky='nsew')
        self.page.grid_columnconfigure(0,weight=1)
        self.page.grid_rowconfigure(0,weight=0)
        self.page.grid_rowconfigure(1,weight=0)
        self.page.grid_rowconfigure(2,weight=0)
        self.page.grid_rowconfigure(3,weight=0)
        self.page.grid_rowconfigure(4,weight=0)
        self.page.grid_rowconfigure(5,weight=0)
        header=ct.CTkFrame(self.page,fg_color='transparent');header.grid(row=0,column=0,padx=BODY_SIDE_PADDING,pady=(14,6),sticky='ew')
        self.header=header;header.grid_columnconfigure(0,weight=1)
        brand=ct.CTkFrame(header,fg_color='transparent');self.brand=brand;brand.grid(row=0,column=0,sticky='w')
        ct.CTkLabel(brand,text='染色工坊',font=TITLE_FONT,text_color=INK).pack(anchor='w')
        ct.CTkLabel(brand,text=f'瑪奇 Mobile  /  by 南千和  ·  v{APP_VERSION}',font=SMALL_FONT,text_color=MUTED).pack(anchor='w')
        toolbar=ct.CTkFrame(self.page,fg_color='transparent');toolbar.grid(row=1,column=0,padx=BODY_SIDE_PADDING,pady=(0,8),sticky='ew')
        self.toolbar=toolbar;toolbar.grid_columnconfigure(0,weight=1)
        self.window_button=ct.CTkButton(toolbar,text='游戏窗口 · 自动检测',width=250,height=32,font=BODY_FONT,anchor='w',fg_color='#28364A',command=self.pick_window)
        self.window_button.grid(row=0,column=0,sticky='w')
        self.refresh_window_label()
        self.body_scroll=FixedContentScrollableFrame(self.page,width=initial_content_width,height=SCROLL_VIEWPORT_HEIGHT,fg_color=BG,corner_radius=0)
        # The viewport stays fixed within each card breakpoint and is centered
        # in the page; resizing only changes its position until a breakpoint.
        self.body_scroll.grid(row=2,column=0,padx=BODY_SIDE_PADDING,sticky='')
        self.body_scroll.grid_columnconfigure(0,weight=1)
        self.toolbar_buttons=[
            ct.CTkButton(toolbar,text='保存方案',width=100,height=32,font=BODY_FONT,fg_color='#28364A',command=self.save),
            ct.CTkButton(toolbar,text='寻色记录',width=100,height=32,font=BODY_FONT,fg_color='#28364A',command=self.show_history),
            ct.CTkOptionMenu(toolbar,values=['简体中文','繁體中文','English'],width=115,font=BODY_FONT,command=self.change_language,variable=tk.StringVar(value=i18n.language)),
        ]
        links=ct.CTkFrame(header,fg_color='transparent');self.links=links;links.grid(row=0,column=1,sticky='e')
        self.tutorial_button=ct.CTkButton(links,text='?',width=36,height=36,fg_color='#62D7BD',hover_color='#80E5CF',text_color='#102A27',font=ICON_FONT,command=self.show_tutorial)
        self.tutorial_button.pack(side='right',padx=4)
        self.github_button=ct.CTkButton(links,text='GitHub',width=70,height=32,font=BODY_FONT,fg_color='#28364A',command=lambda:webbrowser.open(GITHUB))
        self.github_button.pack(side='right',padx=4)
        self.support_button=ct.CTkButton(links,text='♥  支持作者',width=100,height=32,font=BODY_FONT,fg_color='#694C91',command=self.show_support)
        self.support_button.pack(side='right',padx=4)
        for column,button in enumerate(self.toolbar_buttons,1):button.grid(row=0,column=column,padx=(8,0),sticky='ew')
        for column in range(1,4):toolbar.grid_columnconfigure(column,weight=0)
        intro=ct.CTkFrame(self.body_scroll,fg_color='transparent');intro.grid(row=0,column=0,padx=8,pady=(0,10),sticky='ew')
        self.intro=intro
        self.intro_labels=[]
        body=ct.CTkFrame(self.body_scroll,width=0,height=CARD_HEIGHT+2*CARD_GAP,fg_color='transparent')
        body.grid(row=1,column=0,sticky='ew');body.grid_propagate(False);self.card_body=body
        for i in range(3):
            body.grid_columnconfigure(i,weight=1,uniform='cards');card=Card(body,i);card.grid(row=0,column=i,padx=CARD_GAP,pady=CARD_GAP);self.cards.append(card)
        # Keep the card viewport centered between the top and bottom bars.
        # The primary controls remain fixed and left aligned.
        # Keep the fixed-height card viewport in normal flow; a weighted row creates large blank bands around it.
        self.page.grid_rowconfigure(2,weight=0)
        controls=ct.CTkFrame(self.page,fg_color='transparent');controls.grid(row=3,column=0,padx=BODY_SIDE_PADDING,pady=(8,4),sticky='ew')
        self.start=ct.CTkButton(controls,text='开始寻色   F8',height=44,width=165,font=(FONT,13,'bold'),fg_color=ACCENT,text_color='#102A27',hover_color='#80E5CF',command=lambda:self.go(activate=True));self.start.grid(row=0,column=0,padx=(0,8),pady=4,sticky='w')
        self.stop_button=ct.CTkButton(controls,text='停止   F9',height=44,width=100,font=BODY_FONT,fg_color='#2B384C',command=self.stop);self.stop_button.grid(row=0,column=1,padx=(0,8),pady=4,sticky='w')
        self.controls=controls;controls.grid_columnconfigure(2,weight=1)
        selected=read_settings(DATA/'settings.json').get('search_strategy','native')
        self.search_strategy=tk.StringVar(value=selected if selected in ('native','atlas') else 'native')
        self.strategy_menu=ct.CTkOptionMenu(controls,values=[str(tr('精准寻色')),str(tr('图像寻色'))],
            width=220,height=30,font=BODY_FONT,command=self.change_search_strategy)
        self.strategy_menu.grid(row=1,column=0,columnspan=2,sticky='w',pady=(4,2))
        self.strategy_menu.set(str(tr('精准寻色' if self.search_strategy.get()=='native' else '图像寻色')))
        self.strategy_note=ct.CTkLabel(controls,text='图像寻色：精准寻色故障时使用。',font=SMALL_FONT,
            text_color=MUTED,anchor='w',justify='left',wraplength=340,height=18)
        self.strategy_note.grid(row=2,column=0,columnspan=3,sticky='w',pady=(2,0))
        status=ct.CTkFrame(self.page,fg_color=PANEL,corner_radius=14);status.grid(row=4,column=0,padx=BODY_SIDE_PADDING,pady=(4,8),sticky='ew');status.grid_columnconfigure(0,weight=1)
        self.status=ct.CTkLabel(status,text='就绪 · 请先选择游戏窗口和目标颜色',font=BODY_FONT,anchor='w',justify='left',wraplength=720,text_color=INK);self.status.grid(row=0,column=0,padx=18,pady=(12,5),sticky='ew')
        self.detail=ct.CTkLabel(status,text='',font=SMALL_FONT,text_color=MUTED,wraplength=720,anchor='w',justify='left')
        self.detail.grid(row=1,column=0,padx=18,pady=(0,8),sticky='ew');self.detail.grid_remove()
        label=ct.CTkLabel(intro,text='适用于港澳台服瑪奇Mobile。游戏中使用本工具可能存在风险，建议谨慎使用。',font=SMALL_FONT,text_color=MUTED,wraplength=320,justify='left',anchor='w');label.pack(fill='x',pady=(0,8));self.intro_labels.append(label)
        self.footer=ct.CTkLabel(self.page,text='F9 随时停止并释放鼠标  ·  切换窗口停止寻色  ·  不自动开启下一瓶染色剂',font=SMALL_FONT,text_color=MUTED,wraplength=340,justify='right');self.footer.grid(row=5,column=0,padx=BODY_SIDE_PADDING,pady=(0,8),sticky='e')
        self._layout_columns=None;self._layout_content_width=None;self._layout_width=None;self._pending_layout_width=None;self._resize_layout_job=None;self._topbars_compact=None
        self.apply_card_layout(3);self.apply_topbar_layout(False)
        self._autosave_job=None;self._loading_profile=False
        self.load()
        for card in self.cards:
            for key in ('enabled','target','alt','mode','tolerance','priority'):
                getattr(card,key).trace_add('write',self.schedule_autosave)
        if self.history:self.display_best(self.history[0])
        self._hotkeys_stop=threading.Event()
        self._hotkey_thread=threading.Thread(target=self.hotkey_loop,daemon=True)
        self._hotkey_thread.start()
        self.after(30,self.tick);self.protocol('WM_DELETE_WINDOW',self.close)
        self.bind('<Configure>',self.schedule_layout,add='+')
        i18n.on_language(self,self.refresh_language)
        self.after(150,self.reflow)
        self._resize_surface=NativeResizeSurface(self)
    def schedule_layout(self,event):
        if event.widget!=self:return
        try:scaling=self.page._get_widget_scaling()
        except (AttributeError,tk.TclError):return
        width=int(event.width/scaling)
        if getattr(getattr(self,'_resize_surface',None),'active',False):
            self._pending_layout_width=width
            return
        if width==getattr(self,'_layout_width',None):
            if self._resize_layout_job is not None:
                try:self.after_cancel(self._resize_layout_job)
                except tk.TclError:pass
                self._resize_layout_job=None
            self._pending_layout_width=None
            return
        self._pending_layout_width=width
        # A pending frame always uses the newest width. Do not postpone it
        # repeatedly while the user is still dragging the window edge.
        if self._resize_layout_job is None:
            self._resize_layout_job=self.after(16,self._run_scheduled_reflow)
    def _run_scheduled_reflow(self):
        self._resize_layout_job=None
        width=self._pending_layout_width
        self._pending_layout_width=None
        if width is not None:self.reflow(width)
    def apply_card_layout(self,columns,content_width=None,viewport_width=None):
        # Cards are deliberately fixed-size.  Only a 1/2/3-column breakpoint
        # changes their grid; the outer viewport may resize independently.
        content_width=columns*(CARD_WIDTH+2*CARD_GAP)
        layout_changed=(columns!=self._layout_columns or
                        content_width!=getattr(self,'_layout_content_width',None))
        if viewport_width is not None:self.body_scroll.set_viewport_width(viewport_width)
        if not layout_changed:return
        self.body_scroll.set_fixed_content_width(content_width,viewport_width)
        self.intro.configure(width=content_width)
        for label in self.intro_labels:label.configure(wraplength=max(280,content_width-24))
        self.card_body.configure(width=content_width,height=((3+columns-1)//columns)*(CARD_HEIGHT+2*CARD_GAP))
        for i in range(3):
            # Only active columns may absorb extra width.  Leaving hidden
            # columns weighted makes a one-column layout reserve two thirds
            # of the row for empty grid tracks, visibly narrowing the card.
            if i < columns:
                self.card_body.grid_columnconfigure(i,weight=1,uniform='cards')
            else:
                self.card_body.grid_columnconfigure(i,weight=0,uniform='')
        for i,card in enumerate(self.cards):
            column=i%columns
            columnspan=columns if columns==2 and i==2 else 1
            if hasattr(card,'configure'):card.configure(width=CARD_WIDTH,height=CARD_HEIGHT)
            card.grid_configure(row=i//columns,column=column,columnspan=columnspan,sticky='')
        self._layout_columns=columns
        self._layout_content_width=content_width
    def apply_topbar_layout(self,compact):
        if compact==self._topbars_compact:return
        if compact:
            self.brand.grid_configure(row=0,column=0,columnspan=2,sticky='w')
            self.links.grid_configure(row=1,column=0,columnspan=2,sticky='e',pady=(6,0))
            self.window_button.grid_configure(row=0,column=0,columnspan=3,sticky='ew')
            for column,button in enumerate(self.toolbar_buttons):
                button.grid_configure(row=1,column=column,padx=(0 if column==0 else 6,0),pady=(6,0),sticky='ew')
                self.toolbar.grid_columnconfigure(column,weight=1,uniform='toolbar')
            for column in range(3):self.header.grid_columnconfigure(column,weight=0,uniform='')
            self.header.grid_columnconfigure(0,weight=1,uniform='top')
        else:
            self.brand.grid_configure(row=0,column=0,columnspan=1,sticky='w')
            self.links.grid_configure(row=0,column=1,columnspan=1,sticky='e',pady=0)
            self.window_button.grid_configure(row=0,column=0,columnspan=1,sticky='w')
            for column,button in enumerate(self.toolbar_buttons,1):
                button.grid_configure(row=0,column=column,padx=(8,0),pady=0,sticky='ew')
                self.toolbar.grid_columnconfigure(column,weight=0,uniform='')
            for column in range(1,3):self.header.grid_columnconfigure(column,weight=0,uniform='')
            self.header.grid_columnconfigure(0,weight=0,uniform='top')
            self.header.grid_columnconfigure(1,weight=1,uniform='top')
        self._topbars_compact=compact
    def reflow(self,width=None):
        if width is None:width=int(self.winfo_width()/self.page._get_widget_scaling())
        columns=columns_for_width(width)
        usable=max(0,int(width)-BODY_SIDE_PADDING*2-SCROLLBAR_WIDTH)
        viewport_width=max(1,usable)
        self.apply_card_layout(columns,viewport_width=viewport_width)
        self.apply_topbar_layout(columns==1)
        # Keep dynamic text inside the actual window.  Fixed 720-DIP wrap
        # lengths overflow narrow windows and leave Tk labels wider than their
        # visible cells, which looks like clipped or broken line wrapping.
        text_wrap=max(180,int(width)-2*BODY_SIDE_PADDING-36)
        if text_wrap!=getattr(self,'_text_wrap_width',None):
            self._text_wrap_width=text_wrap
            for label in (self.status,self.detail):label.configure(wraplength=text_wrap)
            self.footer.configure(wraplength=min(340,text_wrap))
        # Keep the fixed card viewport centered in the responsive page while
        # allowing the header, controls, status and footer to span the window.
        self.page.grid_columnconfigure(0,weight=1)
        # Center the fixed card viewport whenever the outer window is wider
        # than the current card breakpoint; at narrow widths it remains
        # flush with the normal page padding and scrolls horizontally only
        # through the vertical viewport.
        # CTkScrollableFrame.grid() delegates to its outer frame, but Tk's
        # inherited grid_configure() targets the inner canvas-window frame.
        # Regridding that inner frame detaches it from the canvas and breaks
        # scrolling, clipping and redraws. Configure only the outer viewport.
        self.body_scroll._parent_frame.grid_configure(padx=BODY_SIDE_PADDING)
        self._layout_width=int(width)
    def refresh_language(self):
        self.title(f"{tr('染色工坊 · 瑪奇 Mobile')}  v{APP_VERSION}")
        if hasattr(self,'toolbar_buttons'):self.toolbar_buttons[-1].set(i18n.language)
        self.refresh_window_label()
        if hasattr(self,'strategy_menu'):
            self.strategy_menu.configure(values=[str(tr('精准寻色')),str(tr('图像寻色'))])
            self.strategy_menu.set(str(tr('精准寻色' if self.search_strategy.get()=='native' else '图像寻色')))
    def change_search_strategy(self,value):
        if self.busy:
            self.strategy_menu.set(str(tr('精准寻色' if self.search_strategy.get()=='native' else '图像寻色')))
            return
        strategy='native' if value==str(tr('精准寻色')) else 'atlas'
        self.search_strategy.set(strategy);save_settings(DATA/'settings.json',search_strategy=strategy)
        self.schedule_autosave()
    def show_support(self):self._show_dialog('support',support_dialog)
    def show_tutorial(self):self._show_dialog('tutorial',tutorial_dialog)
    def _show_dialog(self,key,factory):
        if not hasattr(self,'_dialogs'):self._dialogs={}
        old=self._dialogs.get(key)
        if old is not None and old.winfo_exists():old.lift();return
        self._dialogs[key]=factory(self)
    def refresh_window_label(self):
        target=self.selected_window
        if target is None:
            try:title=resolve_target().title
            except RuntimeError:title=tr('未检测到唯一窗口')
            text=tr('自动检测')+' · '+title
        else:text=tr('游戏窗口 · ')+target.title
        self.window_button.configure(text=text if len(text)<=34 else text[:31]+'…')
    def pick_window(self):
        if self.busy:
            self.status.configure(text='请先按 F9 停止，再更换游戏窗口。');return
        def selected(target):
            if self.busy:
                self.status.configure(text='请先按 F9 停止，再更换游戏窗口。');return
            self.selected_window=target
            self.refresh_window_label()
            self.status.configure(text='窗口选择已更新，下次开始时生效。')
        WindowPicker(self,self.selected_window,selected)
    def change_language(self,value):
        i18n.set_language(value)
        save_settings(DATA/'settings.json',language=value)
    def display_best(self,row):
        self.best_summary=row
        for c,r in zip(self.cards,row['regions']):
            delta=r['delta'];color=r['color']
            text=f'{color or "—"} · ΔE {delta:.2f}' if delta is not None else f'{color or "—"} · 未参与匹配'
            c.best_label.configure(text=text,fg_color=color or '#28364A',text_color='#17202B' if color and sum(rgb(color))>430 else 'white')
        if row['maximum'] is not None:
            if row.get('outcome')=='compromise':
                prefix='妥协方案（未达目标） · 本次结果'
            else:
                prefix='本次结果' if row.get('outcome') else '最佳组合'
            self.set_detail(tr(prefix)+tr(' · 最大色差 ΔE ')+
                            f'{row["maximum"]:.2f}'+tr(' / 平均 ')+
                            f'{row["average"]:.2f}'+tr(' · 色差越小越接近目标'))
    def set_detail(self,text):
        self.detail.configure(text=text)
        if text:self.detail.grid()
        else:self.detail.grid_remove()
    def show_history(self):
        win=ct.CTkToplevel(self);win.title(tr('寻色记录 · by 南千和'))
        width,height=logical_size(win,(820,620));win.minsize(min(620,width),min(400,height));win.geometry(f'{width}x{height}')
        win.transient(self);win.configure(fg_color=BG)
        ct.CTkLabel(win,text='寻色记录',font=TITLE_FONT).pack(anchor='w',padx=24,pady=(20,4))
        ct.CTkLabel(win,text='记录最近 50 次结果 · ΔE 越小越接近目标，0 表示目标原色',font=BODY_FONT,text_color=MUTED,wraplength=560,justify='left').pack(anchor='w',padx=24,pady=(0,12))
        area=ct.CTkScrollableFrame(win,fg_color=BG);area.pack(fill='both',expand=True,padx=16,pady=(0,16))
        win.after_idle(lambda:win.geometry(f'{width}x{height}') if win.winfo_exists() else None)
        if not self.history:ct.CTkLabel(area,text='完成一次寻色后，颜色组合会自动保存在这里。',font=BODY_FONT).pack(pady=40)
        names={'matched':'目标达标','compromise':'妥协结果','applied':'已套用','observed':'当前色码记录'}
        for row in self.history:
            box=ct.CTkFrame(area,fg_color=PANEL,corner_radius=12);box.pack(fill='x',pady=6)
            title=f'{row["time"]}  ·  {names.get(row.get("outcome"),"寻色结果")}'
            if row['maximum'] is not None:title+=f'  ·  最大 ΔE {row["maximum"]:.2f} / 平均 {row["average"]:.2f}'
            ct.CTkLabel(box,text=title,font=BODY_FONT,anchor='w',wraplength=560,justify='left').pack(fill='x',padx=12,pady=(8,4))
            line=ct.CTkFrame(box,fg_color='transparent');line.pack(fill='x',padx=12,pady=(0,10))
            for index,r in enumerate(row['regions']):
                line.grid_columnconfigure(index,weight=1,uniform='history')
                color=r['color'];delta=r['delta'];text=f'区域 {r["region"]}  {color or "未识别"}'
                text+=f'\n色差 ΔE {delta:.2f}' if delta is not None else '\n未参与匹配'
                ct.CTkLabel(line,text=text,font=SMALL_FONT,width=150,height=52,corner_radius=8,fg_color=color or '#28364A',text_color='#17202B' if color and sum(rgb(color))>430 else 'white').grid(row=0,column=index,sticky='ew',padx=3)
    def _set_scaling(self,new_widget_scaling,new_window_scaling):
        surface=getattr(self,'_resize_surface',None)
        if surface is not None:surface.hold_scaling()
        # CTk otherwise pins min/max size for one second even when only font /
        # widget scaling changes. Never re-enter window geometry for that case.
        if abs(new_window_scaling-self._get_window_scaling())<.001:
            CTkScalingBaseClass._set_scaling(self,new_widget_scaling,new_window_scaling)
        else:super()._set_scaling(new_widget_scaling,new_window_scaling)
    def fit_screen(self):
        # Choose density once. Window gestures must never change widget/font
        # scaling: CTk scaling recursively redraws and reconfigures every child.
        dpi=self._get_window_scaling()
        _,_,screen_width,screen_height=work_area(self)
        available_width=max(1,int(screen_width/dpi)-80)
        available_height=max(1,int(screen_height/dpi)-100)
        self._ui_scale=min(1.,max(.7,available_height/860))
        ct.set_widget_scaling(self._ui_scale)
        self.update_idletasks()
        minimum_width=min(MIN_WINDOW_WIDTH,available_width)
        # ``geometry()`` and ``minsize()`` take CTk's logical window units,
        # while the widgets use the independent widget scale above.  On a
        # high-DPI monitor the latter is intentionally capped at 1.0, so
        # ``page.winfo_reqheight()`` is a native/Tk pixel size.  Passing that
        # value directly to ``geometry`` makes CTk multiply it by the window
        # DPI a second time (for example 1,243 px becomes 1,914 px), leaving
        # a large empty band below the page.  Convert the requested native
        # size back to the logical units expected by CTk before sizing the
        # toplevel.
        requested_native_height=max(560,self.page.winfo_reqheight())
        requested_logical_height=int((requested_native_height+dpi-1)//dpi)
        minimum_height=min(requested_logical_height,available_height)
        self.minsize(minimum_width,minimum_height)
        width=max(minimum_width,min(1120,available_width))
        # Start at the content height so high-resolution displays do not add
        # a large empty area below the controls. The user can still resize freely.
        height=min(available_height,minimum_height)
        self.geometry(f'{width}x{height}+20+20')
    def current_profile(self):
        return dict(schema=1,regions=[{key:getattr(c,key).get() for key in
            ('enabled','target','alt','mode','tolerance')} for c in self.cards],
            priority_order=sorted(range(3),key=lambda i:self.cards[i].priority.get()),
            search_strategy=self.search_strategy.get())
    def apply_profile(self,profile,*,persist=True):
        if self.busy:raise ValueError('请先停止寻色，再载入方案。')
        profile=canonical_profile(profile)
        self._loading_profile=True
        try:
            for card,row in zip(self.cards,profile['regions']):
                for key in ('enabled','target','alt','mode','tolerance'):getattr(card,key).set(row[key])
                card.change_mode()
            for rank,index in enumerate(profile['priority_order'],1):
                self.cards[index].priority.set(rank);self.cards[index].priority_menu.set(str(rank))
            self.search_strategy.set(profile['search_strategy'])
            self.refresh_language()
        finally:self._loading_profile=False
        if persist and not self.flush_autosave():raise OSError('设置未能自动保存，请检查数据目录是否可写。')
    def set_card_priority(self,index,rank):
        if self.busy:
            self.cards[index].priority_menu.set(str(self.cards[index].priority.get()));return
        previous=self.cards[index].priority.get()
        for card in self.cards:
            if card.index!=index and card.priority.get()==rank:
                card.priority.set(previous);card.priority_menu.set(str(previous))
        self.cards[index].priority.set(rank);self.cards[index].priority_menu.set(str(rank))
        self.schedule_autosave()
    def schedule_autosave(self,*_):
        if getattr(self,'_loading_profile',False):return
        job=getattr(self,'_autosave_job',None)
        if job is not None:
            try:self.after_cancel(job)
            except tk.TclError:pass
        self._autosave_job=self.after(300,self.flush_autosave)
    def flush_autosave(self):
        job=getattr(self,'_autosave_job',None)
        if job is not None:
            try:self.after_cancel(job)
            except tk.TclError:pass
        self._autosave_job=None
        try:
            write_profile(DATA/'profile.json',self.current_profile());self._profile_read_failed=False;return True
        except (OSError,ValueError):
            self.set_detail(tr('设置未能自动保存，请检查数据目录是否可写。'));return False
    def save(self):
        from ui_presets import PresetDialog
        self._show_dialog('presets',lambda parent:PresetDialog(parent,PresetStore(DATA/'presets.json'),
            self.current_profile,self.apply_profile))
    def load(self):
        try:profile=read_profile(DATA/'profile.json',search_strategy=self.search_strategy.get())
        except (OSError,ValueError):
            from profile_store import default_profile
            profile=default_profile();profile['search_strategy']=self.search_strategy.get()
            self._profile_read_failed=True
            self.set_detail(tr('当前设置无法读取，原文件已保留。'))
        self.apply_profile(profile,persist=False)
    def go(self,mode='search',activate=False):
        if self.busy:
            self.status.configure(text='任务已启动，正在等待或寻色；按 F9 停止。');return
        if self.picking:return
        try:
            rules=[dict(c.rule(),priority=c.priority.get()) for c in self.cards]
            if not getattr(self,'_profile_read_failed',False) or getattr(self,'_autosave_job',None) is not None:self.flush_autosave()
            if mode=='search' and not any(r['enabled'] for r in rules):raise ValueError('请至少启用一个颜色区域。')
        except ValueError as e:self.status.configure(text=str(e));return
        strategy=self.search_strategy.get() if mode=='search' else 'legacy'
        runtime_strategy=strategy
        target=self.selected_window
        self.active_rules=rules
        self.active_mode=mode
        self.busy=True;self.start.configure(state='disabled');self.status.configure(text='正在识别游戏界面…')
        session_root=DATA/'sessions'
        start_session_cleanup(session_root)
        folder=new_session_path(session_root)
        try:self.runner=build_runner(lambda k,d:self.q.put((k,d)),folder,strategy)
        except (ValueError,RuntimeError) as exc:
            self.busy=False;self.start.configure(state='normal');self.status.configure(text=tr(str(exc)));return
        if mode=='search':
            try:
                if self.overlay is None:self.overlay=SearchOverlay(self,self.stop,self.select_candidate,settings_path=DATA/'settings.json')
                self.overlay.begin(rules,passive=strategy=='native')
            except Exception:
                self.set_detail('浮窗暂不可用，寻色状态请查看主窗口。')
        threading.Thread(target=self.runner.launch,args=(rules,mode,False,activate,target),
                         kwargs={'strategy':runtime_strategy},daemon=True).start()
    def select_candidate(self,batch_id,candidate_id):
        if self.runner:self.runner.choose_candidate(batch_id,candidate_id)
    def stop(self):
        if self.runner:self.runner.stop.set()
        self.status.configure(text='正在停止并释放鼠标…' if self.busy else '已停止自动染色，可重新开始。')
        if self.overlay is not None:self.overlay.dismiss()
    def finish_run(self):
        stopped=self.runner is not None and self.runner.stop.is_set()
        self.busy=False;self.runner=None;self.start.configure(state='normal')
        if stopped:
            self.status.configure(text='已停止自动染色，可重新开始。')
            if self.overlay is not None:self.overlay.dismiss()
    def hotkey_loop(self):
        keys=[(1,0x77),(2,0x78)]
        if not getattr(sys,'frozen',False):keys.append((5,0x75))
        def receive(kind,data):
            if kind=='hotkey' and data['id']==2 and self.runner:self.runner.stop.set()
            self.q.put((kind,data))
        run_hotkeys(platform_win.u,ctypes,platform_win.W,self._hotkeys_stop,receive,keys)
    def tick(self):
        try:
            for _ in range(50):
                if self.q.empty():break
                k,d=self.q.get()
                # Result presentation is optional; it must not strand the
                # worker's terminal event or prevent the next UI poll.
                try:
                    if self.overlay is not None:self.overlay.handle(k,d)
                except Exception:self.report_callback_exception(*sys.exc_info())
                try:self.handle_event(k,d)
                except Exception:self.report_callback_exception(*sys.exc_info())
        finally:self.after(60,self.tick)
    def handle_event(self,k,d):
        if k=='hotkey':
            if d['id']==1:self.go(activate=True)
            elif d['id']==2:self.stop()
            elif d['id']==5:self.go('recovery_test')
        elif k=='hotkey_status':
            names={1:'F8',2:'F9',5:'F6'}
            failed=[names[i] for i in d['failed']]
            text=(tr('快捷键已就绪：F8 开始 / F9 停止') if not failed else
                  tr('全局注册不可用：')+', '.join(failed)+tr('；F9 仍通过轮询停止，其他操作请使用按钮。'))
            self.footer.configure(text=text)
        elif k=='window_bound':
            self.set_detail(tr('正在识别窗口：')+d['title'])
            prefix=tr('自动检测')+' · ' if self.selected_window is None else tr('游戏窗口 · ')
            label=prefix+d['title']
            self.window_button.configure(text=label if len(label)<=34 else label[:31]+'…')
        elif k=='targets':
            for c,color in zip(self.cards,d['colors']):
                c.enabled.set(True);c.target.set(color);c.alt.set('')
            self.flush_autosave()
        elif k in ('scene','match','restore_action'):
            for i,(c,color) in enumerate(zip(self.cards,d.get('colors',[]))):
                inactive=self.active_rules is not None and not self.active_rules[i]['enabled']
                c.current.configure(text='当前颜色  '+(color or ('未参与匹配' if inactive else '读取失败')))
            if k=='scene':self.status.configure(text=f'正在寻色 · 游戏剩余 {d.get("seconds") or "—"} 秒')
            elif k=='restore_action':self.status.configure(text=f'正在恢复最佳颜色 · 游戏剩余 {d.get("seconds") or "—"} 秒')
        elif k=='waiting':
            self.status.configure(text=tr('等待染色界面') if d.get('seconds') is None else tr('等待染色界面 · 剩余 ')+str(d['seconds'])+tr(' 秒'))
            self.set_detail(tr(d['message']))
        elif k in ('atlas_progress','single_progress','native_progress'):
            from ui_progress import progress_text
            title,body=progress_text(d)
            self.status.configure(text=tr(title));self.set_detail(tr(body))
        elif k=='native_result':
            from native_status import result_text
            title,detail=result_text(d)
            self.status.configure(text=tr(title));self.set_detail(tr(detail))
            for card,color in zip(self.cards,d.get('actual_colors') or [None]*3):
                card.current.configure(text='当前颜色  '+(color or '读取失败'))
            if d.get('verified') and self.active_rules:
                try:
                    row=save_result(DATA/'history.json',d['actual_colors'],self.active_rules,
                        'matched' if d.get('accepted') else 'compromise' if d.get('outcome')=='compromise' else 'observed',
                        d.get('restored'),d.get('best_actual_colors'))
                    self.history=read_history(DATA/'history.json');self.display_best(row)
                except OSError:self.set_detail(tr('本轮结果未能保存，请检查程序文件夹是否可写。'))
        elif k=='single_verified':
            for i,(card,color) in enumerate(zip(self.cards,d.get('actual_colors') or [None]*3)):
                disabled=self.active_rules is not None and not self.active_rules[i]['enabled']
                card.current.configure(text='当前颜色  '+(color or ('未参与匹配' if disabled else '读取失败')))
            from ui_progress import single_result_presentation
            title,detail=single_result_presentation(d)
            self.status.configure(text=tr(title))
            self.set_detail(tr(detail))
            if d.get('verified') and self.active_rules:
                try:
                    row=save_result(DATA/'history.json',d['actual_colors'],self.active_rules,
                        'matched' if d.get('accepted') else 'compromise',
                        d.get('restored'),d.get('best_actual_colors'))
                    self.history=read_history(DATA/'history.json');self.display_best(row)
                except OSError:self.set_detail(tr('本轮结果未能保存，请检查程序文件夹是否可写。'))
        elif k=='atlas_status':
            self.status.configure(text=tr('自动染色'))
            self.set_detail(tr(d.get('message','')))
        elif k=='atlas_ready':self.status.configure(text=tr('本局颜色板质量门槛通过，正在准备自动最佳方案。'))
        elif k in ('atlas_default_verified','atlas_verified'):
            colors=d.get('actual_colors',d.get('colors',[]))
            for card,color in zip(self.cards,colors):card.current.configure(text='当前颜色  '+(color or '读取失败'))
            self.status.configure(text='当前结果已达到所设目标，请在游戏内手动确认。' if d.get('accepted') else '当前结果未达到全部目标；请先查看妥协方案，再在游戏内手动确认是否套用。')
        elif k=='atlas_best_not_restored':
            for card,color in zip(self.cards,d.get('actual_colors') or [None]*3):
                card.current.configure(text='当前颜色  '+(color or '读取失败'))
            self.status.configure(text=tr('未能恢复先前最佳结果，请以游戏当前颜色为准。'))
        elif k=='atlas_default_unavailable':self.status.configure(text=tr(d.get('message','剩余时间不足，未发送定位操作。')))
        elif k=='atlas_invalidated':self.status.configure(text=tr(d.get('message','颜色板质量未达标，未发布候选。')))
        elif k=='atlas_choice_rejected':self.status.configure(text=tr(d.get('message','剩余时间不足，保持自动最佳方案。')))
        elif k=='atlas_selection_expired':self.status.configure(text=tr('未选择其他方案，保持自动最佳方案。'))
        elif k in ('wait_timeout','interrupted'):
            self.status.configure(text=tr(d['message']))
            if not (self.runner is not None and self.runner.stop.is_set()):
                self.after(100,lambda m=d['message']:messagebox.showinfo(tr('流程已中断'),tr(m),parent=self))
        elif k=='action':self.set_detail('正在调整色板，持续寻找更接近的颜色…')
        elif k in ('explore','restoring','magnifying','restore_fallback','input_recheck','activation'):self.set_detail(d['message'])
        elif k=='best':
            if self.active_rules:self.display_best(describe_result(d['colors'],self.active_rules))
        elif k in ('error','done'):
            self.status.configure(text=d.get('message',''))
            if k=='error':
                self.after(100,lambda m=d.get('message',''):messagebox.showerror(tr('流程已中断'),tr(m),parent=self))
            elif not d.get('popup') and getattr(self,'active_mode','search')=='search':
                self.after(100,lambda m=d.get('message',''):messagebox.showinfo(tr('流程已中断'),tr(m),parent=self))
            for c,color in zip(self.cards,d.get('colors',[])):c.current.configure(text='当前颜色  '+(color or '读取失败'))
            if d.get('popup'):
                if self.active_rules:
                    try:
                        row=save_result(DATA/'history.json',d.get('colors',[]),self.active_rules,d.get('outcome'),d.get('restored'),d.get('best_colors'))
                        self.history=read_history(DATA/'history.json');self.display_best(row)
                    except OSError:self.set_detail('本轮结果未能保存，请检查程序文件夹是否可写。')
                message=d['message']+'\n\n当前颜色：'+' / '.join(c or '未识别' for c in d.get('colors',[]))
                self.after(100,lambda m=message,o=d.get('outcome'):messagebox.showinfo(tr('流程完成 · '+('妥协结果' if o=='compromise' else '目标达标')),tr(m),parent=self))
        elif k=='finished':self.finish_run()
    def close(self):
        if self.busy:self.stop();self.after(250,self.close)
        else:
            if not getattr(self,'_profile_read_failed',False) or getattr(self,'_autosave_job',None) is not None:self.flush_autosave()
            self._hotkeys_stop.set()
            if hasattr(self,'_resize_surface'):self._resize_surface.destroy()
            self._resize_redraw.restore()
            self.destroy()

if __name__=='__main__':App().mainloop()
