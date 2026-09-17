"""Non-activating search status surface; never issues game input."""
import ctypes as C
from ctypes import wintypes as W
import customtkinter as ct
from i18n import tr
from vision import accepted

class SearchOverlay(ct.CTkToplevel):
    def __init__(self,parent,stop):
        super().__init__(parent)
        self.withdraw();self.overrideredirect(True);self.attributes('-topmost',True)
        self.configure(fg_color='#131F2C');self.rules=[];self.phase='waiting';self._text=None
        self.geometry(f'390x170+{max(0,self.winfo_screenwidth()-round(390*self._get_window_scaling())-24)}+35')
        self.grid_columnconfigure(0,weight=1)
        self.heading=ct.CTkLabel(self,text='等待染色界面',font=('Microsoft YaHei UI',16,'bold'),anchor='w',text_color='#62D7BD')
        self.heading.grid(row=0,column=0,padx=16,pady=(10,2),sticky='ew')
        self.copy=ct.CTkLabel(self,text='',font=('Microsoft YaHei UI',12),justify='left',anchor='w',wraplength=355)
        self.copy.grid(row=1,column=0,padx=16,pady=4,sticky='ew')
        ct.CTkButton(self,text='满意当前颜色？停止接管 F9',height=32,fg_color='#236D62',command=stop).grid(row=2,column=0,padx=16,pady=(4,10),sticky='ew')
        self.heading.bind('<Button-1>',self._drag_start)
        self.heading.bind('<B1-Motion>',self._drag)
        self.update_idletasks()
        self._prepare_native()
    def _prepare_native(self):
        user=C.windll.user32
        user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
        self.native=user.GetAncestor(self.winfo_id(),2)
        user.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];user.GetWindowLongPtrW.restype=C.c_ssize_t
        user.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t];user.SetWindowLongPtrW.restype=C.c_ssize_t
        style=user.GetWindowLongPtrW(self.native,-20)
        user.SetWindowLongPtrW(self.native,-20,style|0x08000000|0x80) # NOACTIVATE, TOOLWINDOW
        user.SetWindowDisplayAffinity.argtypes=[W.HWND,W.DWORD]
        user.SetWindowDisplayAffinity(self.native,0x11) # exclude status surface from capture where supported
    def _drag_start(self,event):
        self._drag_offset=(event.x_root-self.winfo_x(),event.y_root-self.winfo_y())
    def _drag(self,event):
        x,y=self._drag_offset;self.geometry(f'+{max(0,event.x_root-x)}+{max(0,event.y_root-y)}')
    def begin(self,rules):
        self.rules=rules;self.phase='waiting';self.render('等待染色界面','可从任意游戏界面进入普通染色并完成教学。\n识别成功后自动寻色；F9 取消等待。')
        self._prepare_native();self.deiconify()
    def render(self,title,body):
        value=(title,body)
        if value==self._text:return
        self._text=value;self.heading.configure(text=tr(title));self.copy.configure(text=tr(body))
    def handle(self,kind,data):
        if kind=='waiting':
            self.phase='waiting';self.render('等待染色界面','可从任意游戏界面进入普通染色并完成教学。\n识别成功后自动寻色；F9 取消等待。')
        elif kind in ('restoring','restore_action','restore_fallback'):
            self.phase='restoring';self.render('正在回退 · 随时可按 F9 接管','正在恢复本轮最佳组合，结束前提前停止微调。\n满意当前颜色时，按 F9 保留当前画面。')
        elif kind in ('scene','action') and self.phase!='restoring':
            self.phase='searching'
            colors=data.get('colors',data.get('after',[]))
            title='当前组合已达标 · 仍在优化' if accepted(colors,self.rules) else '持续搜索最佳颜色组合'
            self.render(title,'剩余约 30 秒回退最佳方案。\n满意当前颜色时请按 F9 停止，由你确认使用。')
        elif kind=='input_recheck':
            self.render('正在复查画面变化','尚未确认输入失败，请稍候。\n满意当前颜色时仍可按 F9 接管。')
        elif kind in ('done','error','interrupted','wait_timeout','finished'):
            self.withdraw()
