"""Non-activating search status surface; never issues game input."""
import ctypes as C
from ctypes import wintypes as W
from tkinter import TclError
import customtkinter as ct
import time
from ui_settings import read_settings,save_settings
from ui_progress import progress_text,single_result_presentation
from ui_performance import DeliberateSlider
from i18n import tr,on_language
from display_geometry import work_area,clamp_position
from vision import accepted
from ui_typography import SECTION_FONT,BODY_FONT,SMALL_FONT
from overlay_native import configure_overlay,unregister_overlay


def candidate_display(row, result=None):
    """Keep game observations separate from forecasts and execution targets."""
    if not result or not result.get('verified') or not result.get('actual_colors'):
        return dict(row, measured=False)
    shown=dict(row,measured=True,colors=list(result['actual_colors']),
               deltas=list(result.get('actual_deltas') or [None]*3))
    for key in ('maximum','average','accepted','exact_matches','exact_total',
                'family_consistent','family_maximum','family_average'):
        if key in result:shown[key]=result[key]
    return shown


def update_candidate_display(data, candidate_id, *, candidate=None, result=None, current=False):
    """Update only the presentation model; preserve selectable candidate IDs."""
    updated=dict(data,candidates=list(data.get('candidates',[])),
                 observations=dict(data.get('observations',{})))
    targets=data.get('candidate_targets') or {row['id']:dict(row) for row in data.get('candidates',[])}
    updated['candidate_targets']=targets
    if candidate is not None:
        updated['candidates']=[dict(candidate) if row['id']==candidate_id else row
                               for row in updated['candidates']]
        updated['observations'].pop(candidate_id,None)
    if result is not None and result.get('verified'):
        updated['observations'][candidate_id]=dict(result)
    if current:
        updated['default_id']=candidate_id
        # Other buttons still execute their published targets. A fallback
        # reached under the same ID must not become their displayed forecast.
        updated['candidates']=[row if row['id']==candidate_id else targets.get(row['id'],row)
                               for row in updated['candidates']]
        updated['candidates'].sort(key=lambda row:row['id']!=candidate_id)
    return updated


def clamp_surface_position(position, screen_size, surface_size):
    """Keep a saved overlay position inside the physical work area.

    ``CTkToplevel.geometry`` accepts logical width/height but native Tk
    reports ``winfo_*`` and event root coordinates in physical pixels.  The
    position itself is not scaled by CustomTkinter, so this helper deliberately
    works only with the native (physical) dimensions.
    """
    sw, sh = (max(1, int(value)) for value in screen_size)
    ww, wh = (max(1, int(value)) for value in surface_size)
    x, y = (int(value) for value in position[:2])
    return (min(max(0, x), max(0, sw - ww)),
            min(max(0, y), max(0, sh - wh)))


def clamp_virtual_surface_position(position, virtual_rect, surface_size):
    """Clamp a native overlay to the complete virtual desktop.

    ``winfo_screen*`` describes the primary monitor.  A saved or dragged
    overlay can legitimately sit on a monitor to the left/above it, so use
    SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN and the virtual width/height instead.
    """
    left, top, width, height = (int(value) for value in virtual_rect)
    ww, wh = (max(1, int(value)) for value in surface_size)
    x, y = (int(value) for value in position[:2])
    return (min(max(left, x), left + max(0, width - ww)),
            min(max(top, y), top + max(0, height - wh)))


def virtual_screen_rect(user32=C.windll.user32):
    """Return the physical virtual-desktop rectangle on Windows."""
    return tuple(int(user32.GetSystemMetrics(index)) for index in (76, 77, 78, 79))

class SearchOverlay(ct.CTkToplevel):
    def __init__(self,parent,stop,select_candidate=None,settings_path=None):
        super().__init__(parent)
        self.withdraw();self.overrideredirect(True);self.attributes('-topmost',True)
        self.configure(fg_color='#131F2C');self.rules=[];self.phase='waiting';self._text=None
        self.select_candidate=select_candidate;self.candidate_rows={};self.batch_id=None;self.stop_action=stop
        self.default_candidate_id=None
        self.settings_path=settings_path;self.preferences=read_settings(settings_path) if settings_path else {}
        self._collapsed=False;self._has_results=False;self._heartbeat_job=None;self._alpha_job=None
        self._surface_job=None;self._native_job=None;self._passive_input=False
        self._started=time.monotonic();self._stage_started=self._started;self._stage=None;self._deadline=None
        self.geometry('410x280+20+100')
        self.attributes('-alpha',max(.65,min(1.,float(self.preferences.get('overlay_alpha',.92)))))
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(1,weight=1)
        self.heading=ct.CTkLabel(self,text='等待染色界面',font=SECTION_FONT,anchor='w',text_color='#62D7BD',wraplength=374)
        self.heading.grid(row=0,column=0,padx=16,pady=(10,2),sticky='ew')
        # Scroll status text and candidates together. The heading and stop
        # control stay accessible even on a short, highly scaled display.
        self.content=ct.CTkScrollableFrame(self,fg_color='transparent',corner_radius=0)
        self.content.grid(row=1,column=0,padx=8,sticky='nsew');self.content.grid_columnconfigure(0,weight=1)
        self.copy=ct.CTkLabel(self.content,text='',font=BODY_FONT,justify='left',anchor='w',wraplength=350)
        self.copy.grid(row=0,column=0,padx=8,pady=4,sticky='ew')
        self.stop_button=ct.CTkButton(self,text='停止 F9',height=32,font=BODY_FONT,fg_color='#236D62',command=stop)
        self.stop_button.grid(row=2,column=0,padx=16,pady=(4,10),sticky='ew')
        self.activity=ct.CTkProgressBar(self.content,height=4,mode='indeterminate',progress_color='#62D7BD')
        self.activity.grid(row=1,column=0,padx=8,pady=6,sticky='ew')
        self.elapsed=ct.CTkLabel(self.content,text='',font=SMALL_FONT,anchor='w',text_color='#94A4B8',wraplength=350)
        self.elapsed.grid(row=2,column=0,padx=8,sticky='ew')
        settings=ct.CTkFrame(self.content,fg_color='transparent');settings.grid(row=3,column=0,padx=8,pady=5,sticky='ew')
        settings.grid_columnconfigure(1,weight=1)
        ct.CTkLabel(settings,text='不透明度',font=SMALL_FONT).grid(row=0,column=0,padx=(0,8))
        self.opacity=DeliberateSlider(settings,from_=.65,to=1,width=130,command=self.set_opacity)
        self.opacity.set(float(self.preferences.get('overlay_alpha',.92)));self.opacity.grid(row=0,column=1,sticky='ew')
        self.collapse=ct.CTkButton(settings,text='收起',width=76,height=26,font=SMALL_FONT,fg_color='#28364A',command=self.toggle_collapse)
        self.collapse.grid(row=0,column=2,padx=(10,0))
        self.results=ct.CTkFrame(self.content,fg_color='#131F2C')
        self.heading.bind('<Button-1>',self._drag_start)
        self.heading.bind('<B1-Motion>',self._drag)
        self.heading.bind('<ButtonRelease-1>',self.save_position)
        # CTkToplevel installs a global Button-1 focus_set handler. Child
        # handlers run before this toplevel tag; stop only the later global
        # focus handler so overlay chrome works without activating the game.
        self.bind('<Button-1>',lambda _event:'break',add='+')
        self.update_idletasks()
        self._prepare_native()
        self.bind('<Map>',self._native_mapped,add='+')
        self.bind('<Destroy>',self._native_destroyed,add='+')
        on_language(self,self.schedule_surface_resize)
    def schedule_surface_resize(self):
        if self._surface_job is None:self._surface_job=self.after_idle(self.resize_surface)
    def _set_scaling(self,new_widget_scaling,new_window_scaling):
        super()._set_scaling(new_widget_scaling,new_window_scaling)
        if hasattr(self,'_surface_job'):self.schedule_surface_resize()
    def _set_scaled_min_max(self):
        super()._set_scaled_min_max()
        if hasattr(self,'_surface_job'):self.schedule_surface_resize()
    def _prepare_native(self):
        user=C.windll.user32
        user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
        native=user.GetAncestor(self.winfo_id(),2)
        previous=getattr(self,'native',None)
        if previous is not None and previous!=native:unregister_overlay(previous)
        self.native=native
        try:self._native_policy=configure_overlay(native,passive=getattr(self,'_passive_input',False))
        except (OSError,TclError):unregister_overlay(native);self.withdraw();raise
    def _native_mapped(self,event):
        if event.widget is self and not getattr(self,'_dismissed',True):
            if getattr(self,'_native_job',None) is not None:self.after_cancel(self._native_job)
            self._native_job=self.after_idle(self._refresh_native)
    def _refresh_native(self):
        self._native_job=None
        if getattr(self,'_dismissed',True):return
        try:self._prepare_native()
        except (OSError,TclError) as exc:
            self._native_error=str(exc);self.withdraw()
    def _native_destroyed(self,event):
        if event.widget is self and getattr(self,'native',None) is not None:unregister_overlay(self.native)
    def set_passive_input(self,enabled):
        self._passive_input=bool(enabled)
        if getattr(self,'native',None) is not None and not getattr(self,'_dismissed',True):self._prepare_native()
    def _drag_start(self,event):
        self._drag_offset=(event.x_root-self.winfo_x(),event.y_root-self.winfo_y())
    def _drag(self,event):
        x,y=self._drag_offset
        position=(event.x_root-x,event.y_root-y)
        px,py=clamp_position(position,work_area(self,position),
                             (self.winfo_width(),self.winfo_height()))
        self.geometry(f'+{px}+{py}')
    def save_position(self,event=None):
        if self.settings_path:save_settings(self.settings_path,overlay_position=[self.winfo_x(),self.winfo_y()])
    def set_opacity(self,value):
        self.attributes('-alpha',value)
        if self._alpha_job:self.after_cancel(self._alpha_job)
        if self.settings_path:self._alpha_job=self.after(250,lambda:save_settings(self.settings_path,overlay_alpha=float(value)))
    def resize_surface(self):
        if self._surface_job is not None:self.after_cancel(self._surface_job);self._surface_job=None
        area=work_area(self);scale=self._get_window_scaling()
        height=175 if self._collapsed else 580 if self._has_results else 280
        width=max(1,min(410,int(area[2]/scale)))
        height=max(1,min(height,int(area[3]/scale)))
        x,y=clamp_position((self.winfo_x(),self.winfo_y()),area,
                           (round(width*scale),round(height*scale)))
        self.geometry(f'{width}x{height}+{x}+{y}')
        wrap=max(80,int(width*scale/self.copy._get_widget_scaling())-60)
        for label in (self.heading,self.copy,self.elapsed):label.configure(wraplength=wrap)
        if getattr(self,'default_result_label',None) is not None:
            self.default_result_label.configure(wraplength=wrap)
    def toggle_collapse(self):
        self._collapsed=not self._collapsed
        self.collapse.configure(text='展开' if self._collapsed else '收起')
        if self._collapsed:self.copy.grid_remove();self.activity.grid_remove();self.results.grid_remove()
        else:
            self.copy.grid();self.activity.grid()
            if self._has_results:self.results.grid()
        self.resize_surface()
    def update_activity(self,data):
        stage=data.get('stage')
        if stage!=self._stage:self._stage=stage;self._stage_started=time.monotonic()
        if 'remaining' in data:self._deadline=time.monotonic()+data['remaining']
        self.activity.stop()
        if data.get('total'):
            self.activity.configure(mode='determinate');self.activity.set(data.get('current',0)/data['total'])
        else:self.activity.configure(mode='indeterminate');self.activity.start()
    def heartbeat(self):
        self._heartbeat_job=None
        if getattr(self,'_dismissed',True):return
        try:self._prepare_native()
        except (OSError,TclError) as exc:
            self._native_error=str(exc);self.withdraw();return
        now=time.monotonic()
        text=f'已用 {int(now-self._started)} 秒 · 本阶段 {int(now-self._stage_started)} 秒'
        if self._deadline is not None:text+=f' · 游戏剩余 {max(0,int(self._deadline-now))} 秒'
        self.elapsed.configure(text=text)
        self._heartbeat_job=self.after(1000,self.heartbeat)
    def begin(self,rules,*,passive=False):
        self._dismissed=False
        self._native_run=False
        self._native_candidate_run=False;self._native_candidate_batch=None;self._native_candidate_closed=False
        self.stop_button.configure(text='停止 F9',command=self.stop_action)
        # Older callers pass passive=True for native runs. Controls must stay
        # reachable while reading/planning; Game scopes suppress the surface
        # only around an actual gesture, without changing the foreground.
        self._passive_input=False
        self._started=time.monotonic();self._stage_started=self._started;self._stage=None;self._deadline=None
        position=self.preferences.get('overlay_position',[20,100])
        # Width/height returned by winfo are native physical pixels.  Using
        # fixed logical constants here put the overlay off-screen at 125%+
        # DPI because CTk scales the 410x280 geometry.
        self.update_idletasks()
        x,y=clamp_position(position,work_area(self,position),
                            (self.winfo_width(),self.winfo_height()))
        self.geometry(f'+{x}+{y}')
        self.clear_candidates()
        self.rules=rules;self.phase='waiting';self.render('等待染色界面','可从任意游戏界面进入普通染色并完成教学。\n识别成功后自动寻色；F9 取消等待。')
        self._prepare_native();self.deiconify();self._prepare_native()
        self._native_job=self.after_idle(self._refresh_native)
        self.schedule_surface_resize()
        self.update_activity({'stage':'waiting'})
        if self._heartbeat_job:self.after_cancel(self._heartbeat_job)
        self.heartbeat()
    def dismiss(self):
        """F9 relinquishes the screen as well as stopping the input worker.

        Queued progress/finished events must not revive a dismissed surface.
        A new begin() explicitly opens the next session.
        """
        self._dismissed=True;self.phase='stopped';self.batch_id=None;self.selection_sent=True
        for button in self.candidate_rows.values():button.configure(state='disabled')
        if hasattr(self,'activity'):self.activity.stop()
        if getattr(self,'_heartbeat_job',None):self.after_cancel(self._heartbeat_job);self._heartbeat_job=None
        if getattr(self,'_native_job',None):self.after_cancel(self._native_job);self._native_job=None
        if getattr(self,'native',None) is not None:unregister_overlay(self.native)
        self.withdraw()
    def render(self,title,body):
        value=(title,body)
        if value==self._text:return
        self._text=value;self.heading.configure(text=tr(title));self.copy.configure(text=tr(body))
    def clear_candidates(self):
        self._candidate_data=None
        self.batch_id=None;self.default_candidate_id=None;self.candidate_rows={};self.selection_sent=False
        for child in self.results.winfo_children():child.destroy()
        self.candidate_container=None;self.default_result_label=None
        self.results.grid_remove();self._has_results=False;self.resize_surface()
    def show_candidates(self,data):
        self.clear_candidates();self.batch_id=data['batch_id'];self.phase='positioning'
        self._candidate_data=dict(data,candidates=list(data.get('candidates',[])))
        rows=data.get('candidates',[])
        default=data.get('default_id');self.default_candidate_id=default
        native=data.get('strategy')=='native'
        if native:
            self.render('本轮候选方案','候选按区域优先级与色差排序')
        elif data.get('compromise_only') or data.get('family_unavailable'):
            self.render('自动定位最接近方案',data.get('message') or
                        '未找到满足所设目标的组合，正在定位最接近的妥协方案。')
        else:
            self.render('自动定位最佳方案','正在定位预测达标且剩余时间允许的方案。\n完成后仍可选择其他方案，实际染色须在游戏内手动确认。')
        self.results.grid(row=4,column=0,padx=2,pady=(0,10),sticky='ew')
        self._has_results=True;self._collapsed=False;self.copy.grid();self.activity.grid();self.collapse.configure(text='收起');self.resize_surface()
        self.candidate_container=ct.CTkFrame(self.results,fg_color='transparent')
        self.candidate_container.pack(fill='x')
        if not rows:
            ct.CTkLabel(self.candidate_container,text='有效覆盖不足，暂无可计算方案。').pack(padx=8,pady=12)
        if data.get('compromise_only'):
            ct.CTkLabel(self.candidate_container,
                        text=tr('本轮没有预测达标方案；以下结果仅供参考，实际复核未达标时会停止。'),
                        font=SMALL_FONT,text_color='#F2C879',wraplength=520,
                        anchor='w',justify='left').pack(fill='x',padx=6,pady=(0,5))
        for row in rows:
            result=data.get('observations',{}).get(row['id']) if native or row['id']==default else None
            shown=candidate_display(row,result)
            frame=ct.CTkFrame(self.candidate_container);frame.pack(fill='x',pady=4)
            title=('当前方案 · 游戏实测' if row['id']==default else '已测试方案 · 游戏实测') if shown['measured'] else '候选方案 · 预测颜色'
            ct.CTkLabel(frame,text=title,font=BODY_FONT).pack(anchor='w',padx=6,pady=(4,2))
            for i,(color,delta) in enumerate(zip(shown['colors'],shown['deltas'])):
                text=f'区域 {i+1}  {color}   ΔE {delta:.2f}' if delta is not None else f'区域 {i+1}  '+(color+' · ' if color else '')+'未参与匹配'
                line=ct.CTkFrame(frame,fg_color='transparent');line.pack(fill='x',padx=6)
                ct.CTkLabel(line,text='',width=18,height=18,fg_color=color or '#333333').pack(side='left',padx=(0,6))
                ct.CTkLabel(line,text=text,font=BODY_FONT).pack(side='left')
            exact_total=int(shown.get('exact_total',0))
            exact_prefix=(tr('精准命中 ')+f"{int(shown.get('exact_matches',0))}/{exact_total} · "
                          if exact_total else '')
            label=exact_prefix+f"最大 {shown['maximum']:.2f} / 平均 {shown['average']:.2f} · "+(('实测达标' if shown['measured'] else '预测达标') if shown['accepted'] else '未精准匹配 · 妥协方案' if exact_total and shown.get('exact_matches',0)<exact_total else '妥协方案')
            if shown.get('family_consistent') is False:label+=' · '+tr('存在色系偏离')
            ct.CTkLabel(frame,text=label,font=BODY_FONT).pack()
            button=ct.CTkButton(frame,text='选择此方案',state='disabled',
                               command=lambda b=self.batch_id,r=row['id']:self.choose(b,r))
            button.pack(fill='x',padx=6,pady=6);self.candidate_rows[row['id']]=button
        if default in self.candidate_rows:
            measured=bool(data.get('observations',{}).get(default,{}).get('verified'))
            self.candidate_rows[default].configure(text=('当前方案（实测）' if measured else '当前方案')
                                                  if native else '自动方案（当前）' if measured else '正在定位此方案')
    def show_native_candidates(self,data,*,ready=False,readonly=False):
        """Keep the worker's ranked targets separate from measured observations."""
        owned=dict(data,strategy='native',default_id=data.get('current_candidate_id',data.get('default_id')),
                   candidates=[dict(row) for row in data.get('candidates',[])],
                   observations=dict(data.get('observations',{})))
        self.show_candidates(owned)
        self._native_run=True;self._native_candidate_run=True
        self._native_candidate_batch=data['batch_id']
        self.phase='verified' if readonly else 'choosing' if ready else 'computing'
        if readonly:self.batch_id=None;self.selection_sent=True
        self.set_passive_input(False)
        self.activity.stop();self.activity.set(1)
        self._deadline=data.get('effective_deadline')
        for row in owned['candidates']:
            enabled=(ready and not readonly and row.get('available',True)
                     and row['id']!=owned['default_id'] and self.select_candidate is not None)
            self.candidate_rows[row['id']].configure(state='normal' if enabled else 'disabled')
        self.render('本轮候选方案','候选选择已结束，以下方案仅供查看。' if readonly else
                    '当前颜色已复核，可选择其他方案。' if ready else '候选按区域优先级与色差排序')
        if ready:
            self.copy.configure(text=tr('当前颜色已复核，可选择其他方案。')+'\n'+
                                tr('候选按区域优先级与色差排序')+'\n'+
                                tr('可选择其他方案，切换前会核对剩余时间和返回路线。实际染色请在游戏内手动确认。'))
    def update_native_observation(self,data):
        owned=dict(self._candidate_data,observations=dict(self._candidate_data.get('observations',{})))
        colors=data.get('actual_colors') or data.get('current_colors')
        candidate_id=data.get('current_candidate_id')
        if candidate_id is None and data.get('status')!='restored':candidate_id=data.get('candidate_id')
        if candidate_id is None and colors:
            candidate_id=next((row['id'] for row in owned['candidates'] if row['colors']==colors),None)
        owned['current_candidate_id']=candidate_id;owned['default_id']=candidate_id
        if data.get('verified') and data.get('screenshot_verified') and candidate_id is not None:
            owned['observations'][candidate_id]=dict(data,actual_colors=colors)
        return owned
    def reopen_native_candidates(self):
        data=getattr(self,'_candidate_data',None)
        if not getattr(self,'_native_candidate_run',False) or not data:return
        self._dismissed=False
        self.show_native_candidates(data,readonly=True)
        self.stop_button.configure(text='关闭候选',command=self.dismiss)
        self._prepare_native();self.deiconify();self._prepare_native()
    def show_default_verification(self,data):
        result=data.get('result',data)
        colors=result.get('actual_colors')
        if not colors:return
        if self.default_result_label is not None:self.default_result_label.destroy()
        maximum=result.get('maximum')
        text=tr('自动方案实测色码')+'  '+' / '.join(color or '—' for color in colors)
        if maximum is not None:text+='\n'+tr('最大实测色差')+f' ΔE {maximum:.2f}'
        if result.get('family_consistent') is False:text+='\n'+tr('部分区域与目标色系不符。')
        self.default_result_label=ct.CTkLabel(self.results,text=text,justify='left',anchor='w',wraplength=374)
        if self.candidate_container is not None:
            self.default_result_label.pack(fill='x',padx=8,pady=(0,8),before=self.candidate_container)
        else:self.default_result_label.pack(fill='x',padx=8,pady=(0,8))
    def choose(self,batch_id,candidate_id):
        if (getattr(self,'phase',None)!='choosing' or getattr(self,'selection_sent',False) or
                batch_id!=self.batch_id or candidate_id not in self.candidate_rows):return
        if getattr(self,'_native_candidate_run',False):
            row=next((row for row in self._candidate_data['candidates'] if row['id']==candidate_id),None)
            if not row or not row.get('available',True) or candidate_id==self.default_candidate_id:return
            self.phase='positioning';self.set_passive_input(False)
        self.selection_sent=True
        for button in self.candidate_rows.values():button.configure(state='disabled')
        self.select_candidate(batch_id,candidate_id)
    def show_verification(self,data):
        self.clear_candidates();self.phase='verified'
        self.results.grid(row=4,column=0,padx=2,pady=(0,10),sticky='ew');self._has_results=True;self._collapsed=False;self.copy.grid();self.activity.grid();self.collapse.configure(text='收起');self.resize_surface()
        self.render('游戏色码已复核','部分区域与目标色系不符。' if data.get('family_consistent') is False else
                    '全部目标达标，请在游戏内手动确认是否套用。' if data['accepted'] else '本轮候选实测未达标；当前颜色如下，尚不能判断色板无解。')
        count=len(data['actual_colors'])
        if count not in (2,3) or len(data['actual_deltas'])!=count:
            raise ValueError('Observed result region counts disagree')
        for i in range(count):
            if data['actual_deltas'][i] is None:continue
            predicted=data.get('predicted_colors',[None]*count)[i]
            delta=data.get('predicted_deltas',[None]*count)[i]
            text=f"区域 {i+1}\n"
            if predicted is not None and delta is not None:
                text+=f"预测 {predicted} · ΔE {delta:.2f}\n"
            text+=f"实测 {data['actual_colors'][i]} · ΔE {data['actual_deltas'][i]:.2f}"
            ct.CTkLabel(self.results,text=tr(text),justify='left',anchor='w').pack(fill='x',padx=8,pady=8)
        ct.CTkLabel(self.results,text=tr(f"最大 {data['maximum']:.2f} / 平均 {data['average']:.2f}")).pack(pady=8)
    def show_recovery(self,data):
        """Render a read-only recovery without assuming a complete pose."""
        candidates=getattr(self,'_candidate_data',None) if data.get('pose_reliable') else None
        self.clear_candidates();self.phase='verified'
        # A measured-pose fallback can resume after this observation. Keep
        # its batch metadata so replanning and final verification can restore
        # the selectable list; the controls stay hidden until that happens.
        if candidates is not None:self._candidate_data=candidates
        self.results.grid(row=4,column=0,padx=2,pady=(0,10),sticky='ew');self._has_results=True;self._collapsed=False;self.copy.grid();self.activity.grid();self.collapse.configure(text='收起');self.resize_surface()
        actual=data.get('actual_colors') or [None]*3
        deltas=data.get('actual_deltas') or [None]*3
        self.render('已停止自动移动',
                    '本次调整未完成，已读取当前游戏颜色。' if data.get('verified') and any(actual)
                    else '未能读取当前色码，请以游戏内显示为准。')
        for i,(color,delta) in enumerate(zip(actual,deltas)):
            if color is None and delta is None:continue
            text=f"区域 {i+1}\n实测 {color or '—'}"+(f" · ΔE {delta:.2f}" if delta is not None else '')
            ct.CTkLabel(self.results,text=tr(text),justify='left',anchor='w').pack(fill='x',padx=8,pady=8)
        maximum=data.get('maximum');average=data.get('average')
        if maximum is not None and average is not None:
            ct.CTkLabel(self.results,text=tr(f"最大 {maximum:.2f} / 平均 {average:.2f}")).pack(pady=8)

    def show_unrestored_best(self,data):
        self.show_recovery(data)
        self.render('已停止自动移动','未能恢复先前最佳结果，请以游戏当前颜色为准。')
        best=data.get('best_result') or {}
        ct.CTkLabel(self.results,text=tr('先前最佳实测（未恢复）'),anchor='w').pack(fill='x',padx=8,pady=8)
        for i,(color,delta) in enumerate(zip(best.get('actual_colors') or [],best.get('actual_deltas') or [])):
            if color is None or delta is None:continue
            ct.CTkLabel(self.results,text=tr(f"区域 {i+1} · {color} · ΔE {delta:.2f}"),
                        anchor='w').pack(fill='x',padx=8,pady=4)
    def show_single_result(self,data):
        self.clear_candidates();self.phase='verified'
        self.results.grid(row=4,column=0,padx=2,pady=(0,10),sticky='ew')
        self._has_results=True;self._collapsed=False;self.copy.grid();self.activity.grid()
        self.collapse.configure(text='收起');self.resize_surface()
        title,body=single_result_presentation(data)
        self.render(title,body)
        for i,(color,delta) in enumerate(zip(data.get('actual_colors') or [None]*3,
                                           data.get('actual_deltas') or [None]*3)):
            if not self.rules[i]['enabled']:continue
            text=f"区域 {i+1}\n"+tr('当前颜色  ')+(color or tr('读取失败'))
            if delta is not None:text+=f" · ΔE {delta:.2f}"
            ct.CTkLabel(self.results,text=tr(text),justify='left',anchor='w').pack(fill='x',padx=8,pady=8)
    def handle(self,kind,data):
        if getattr(self,'_dismissed',False):return
        if kind=='region_layout':
            self.rules=list(data['rules'])
            if data.get('region_count')==2:
                self.render('已识别双区域色板','已识别 2 个染色区域，区域 3 本局不可用。')
            return
        if kind in ('native_candidates','native_candidate_ready'):
            if (getattr(self,'_native_candidate_batch',None) is not None
                    and data.get('batch_id')!=self._native_candidate_batch):return
            if getattr(self,'_native_candidate_closed',False):return
            if kind=='native_candidates':self._native_candidate_closed=False
            self.show_native_candidates(data,ready=kind=='native_candidate_ready');return
        if kind in ('native_candidate_selected','native_candidate_closed'):
            if (data.get('batch_id')!=getattr(self,'_native_candidate_batch',None) or
                    getattr(self,'_native_candidate_closed',False)):return
            if kind=='native_candidate_closed' or data.get('status')=='expired':
                self._native_candidate_closed=True
                self.show_native_candidates(self.update_native_observation(data),readonly=True);return
            status=data.get('status')
            if status=='positioning':
                self.phase='positioning';self.selection_sent=True;self.set_passive_input(False)
                for button in self.candidate_rows.values():button.configure(state='disabled')
                self.render('正在定位所选方案','正在核对当前游戏色码。');return
            if status in ('observed','current','restored') and data.get('screenshot_verified'):
                self.show_native_candidates(self.update_native_observation(data))
                self.render('所选方案已复核','当前颜色已复核，可选择其他方案。')
            elif status=='rejected':
                from native_status import candidate_reason_text
                self.show_native_candidates(self._candidate_data,ready=True)
                self.render('已保留当前方案',candidate_reason_text(data.get('reason')))
            elif status=='recovery_unconfirmed':
                self._native_candidate_closed=True
                self.show_native_candidates(self._candidate_data,readonly=True)
                self.render('已停止自动移动','请以游戏当前颜色为准。')
            return
        if kind in ('native_progress','native_result'):
            self._native_run=True
            if getattr(self,'_passive_input',False):self.set_passive_input(False)
        if kind=='finished' and getattr(self,'_native_run',False):
            # Native results remain in the main window and history. Its
            # topmost surface must release the underlying controls when the
            # worker ends; atlas candidate/result surfaces keep their policy.
            self.dismiss();return
        if kind in ('atlas_progress','single_progress','native_progress'):
            self.phase='waiting' if data.get('stage')=='waiting' else 'computing'
            self.update_activity(data);self.render(*progress_text(data));return
        if kind=='single_action':
            self.phase='computing';self.update_activity({'stage':'restore' if data.get('restoring') else 'position'})
            self.render(*progress_text({'stage':'restore' if data.get('restoring') else 'position'}));return
        if kind=='single_verified':
            self.activity.stop();self.activity.set(1);self.show_single_result(data);return
        if kind=='native_result':
            from native_status import result_text
            self.activity.stop();self.activity.set(1)
            if getattr(self,'_native_candidate_run',False) and getattr(self,'_candidate_data',None):
                owned=self.update_native_observation(data)
                self._native_candidate_closed=True
                self.show_native_candidates(owned,readonly=True)
            else:self.show_recovery(data)
            self.render(*result_text(data));return
        if kind=='atlas_command':
            self.phase='positioning';self.update_activity({'stage':'position'})
            self.render('移动到目标位置',f"步骤 {data.get('step',1)} · 根据图像实测位移校正；F9随时停止。");return
        if kind in ('atlas_default_verified','atlas_verified','atlas_recovery','atlas_best_not_restored','atlas_recovery_unavailable','atlas_invalidated','atlas_default_unavailable','error','interrupted','finished') and hasattr(self,'activity'):
            self.activity.stop();self.activity.set(1)
        if kind=='interrupted' and self.phase in ('choosing','positioning','verified'):
            self.batch_id=None
            for button in self.candidate_rows.values():button.configure(state='disabled')
            self.phase='interrupted';self.render('流程已中断',data.get('message','已停止，请查看游戏当前颜色。'))
        elif kind=='atlas_candidates':
            self.show_candidates(data)
        elif kind in ('atlas_replanned','atlas_prediction_updated') and data.get('candidate') and getattr(self,'_candidate_data',None):
            updated=update_candidate_display(self._candidate_data,data['candidate_id'],
                                             candidate=data['candidate'],current=True)
            self.show_candidates(updated)
        elif kind=='atlas_invalidated':
            self.clear_candidates();self.phase='invalidated'
            title='大图重建校验未通过' if data.get('reason')=='atlas_quality_failed' else '当前搜索未得到可执行方案'
            self.render(title,data['message'])
        elif kind=='atlas_default_unavailable':
            self.clear_candidates();self.phase='unavailable';self.render('剩余时间不足',data.get('message','无法安全定位并复核自动最佳方案。'))
        elif kind=='atlas_positioning':
            self.phase='positioning';self.render('正在定位所选方案','根据图像实测位移校正；F9随时停止。')
        elif kind=='atlas_candidate_failed':
            if getattr(self,'_candidate_data',None):
                self.show_candidates(update_candidate_display(self._candidate_data,data['candidate_id'],result=data))
            self.phase='positioning';self.render('当前候选实测未达标','正在检查剩余候选和游戏时间；F9随时停止。')
        elif kind=='atlas_default_verified':
            if getattr(self,'_candidate_data',None):
                self.show_candidates(update_candidate_display(self._candidate_data,data['candidate_id'],result=data,current=True))
            self.default_candidate_id=data.get('candidate_id',self.default_candidate_id)
            self.phase='choosing'
            if data.get('family_consistent') is False:
                self.render('存在色系偏离','部分区域与目标色系不符。')
            elif data.get('compromise') or not data.get('accepted',True):
                self.render('已到达最接近方案','这是当前可测量的妥协方案；可选择其他方案，实际染色须在游戏内手动确认。')
            else:
                self.render('已到达自动最佳方案','可选择其他方案；剩余时间不足时将保持当前自动方案。')
            self.show_default_verification(data)
            for candidate_id,button in self.candidate_rows.items():
                button.configure(text='自动方案（当前）' if candidate_id==self.default_candidate_id else '选择此方案',
                                 state='normal' if self.select_candidate and candidate_id!=self.default_candidate_id else 'disabled')
        elif kind=='atlas_choice_rejected':
            self.batch_id=None
            for button in self.candidate_rows.values():button.configure(state='disabled')
            self.phase='verified';self.render('已保持自动最佳方案',data.get('message','剩余时间不足，未移动到所选方案。'))
        elif kind=='atlas_selection_expired':
            self.batch_id=None
            for button in self.candidate_rows.values():button.configure(state='disabled')
            self.phase='verified';self.render('未选择其他方案','已保持自动最佳方案。')
        elif kind=='atlas_verified':
            self.show_verification(data)
        elif kind=='atlas_recovery':
            self.show_recovery(data)
        elif kind=='atlas_best_not_restored':
            self.show_unrestored_best(data)
        elif kind=='atlas_status':
            self.render('自动染色',data.get('message',''))
        elif kind=='atlas_recovery_unavailable':
            self.clear_candidates();self.phase='verified'
            self.render('已保留当前画面',data.get('message','当前动作未能可靠复核，已停止自动移动。'))
        elif kind=='atlas_candidate_unavailable':
            # A malformed or unreachable candidate is filtered before any
            # input. Keep the visible workflow alive while the service checks
            # the remaining candidates.
            return
        elif kind=='waiting':
            self.phase='waiting';self.render('等待染色界面',data.get('message','可从任意游戏界面进入普通染色并完成教学。\n识别成功后自动寻色；F9 取消等待。'))
        elif kind=='activation':
            self.render('请点击游戏窗口',data['message'])
        elif kind in ('restoring','restore_action','restore_fallback'):
            self.phase='restoring';self.render('正在回退 · 随时可按 F9 接管','正在恢复本轮最佳组合，结束前提前停止微调。\n如需保留当前画面，请按 F9 停止。')
        elif kind in ('scene','action') and self.phase!='restoring':
            self.phase='searching'
            colors=data.get('colors',data.get('after',[]))
            title='当前组合已达标 · 仍在优化' if accepted(colors,self.rules) else '持续搜索最佳颜色组合'
            self.render(title,'剩余约 30 秒回退最佳方案。\n如需保留当前颜色，请按 F9 停止，并在游戏内手动确认是否套用。')
        elif kind=='input_recheck':
            self.render('正在复查画面变化','尚未确认输入失败，请稍候。\n如需保留当前颜色，仍可按 F9 接管。')
        elif kind in ('done','error','interrupted','wait_timeout','finished'):
            if kind=='finished' and self.phase in ('choosing','positioning'):
                self.batch_id=None
                for button in self.candidate_rows.values():button.configure(state='disabled')
                self.phase='interrupted';self.render('流程已中断','候选选择已结束。')
                return
            if self.phase in ('choosing','positioning','verified','invalidated','unavailable','interrupted') and kind in ('interrupted','finished'):
                return
            if self.phase in ('invalidated','unavailable') and kind=='error':
                return
            self.clear_candidates()
            self.withdraw()
