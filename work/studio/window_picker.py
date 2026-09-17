"""Explicit selection by window identity; titles are display data only."""
import customtkinter as ct
from i18n import tr
from window_target import list_windows,choose_auto,WindowUnavailable,valid_target

class WindowPicker(ct.CTkToplevel):
    def __init__(self,parent,current,selected):
        super().__init__(parent);self.title(tr('选择游戏窗口'));self.geometry('680x350');self.resizable(False,False)
        self.transient(parent);self.selected=selected;self.current=current;self.choices={}
        self.grid_columnconfigure(0,weight=1)
        ct.CTkLabel(self,text='选择游戏窗口',font=('Microsoft YaHei UI',22,'bold')).grid(row=0,column=0,padx=24,pady=(20,8),sticky='w')
        ct.CTkLabel(self,text='默认自动识别瑪奇Mobile，也可选择标题不同的游戏窗口。',wraplength=620,justify='left').grid(row=1,column=0,padx=24,pady=4,sticky='w')
        self.menu=ct.CTkOptionMenu(self,values=[tr('自动检测')],width=610,dynamic_resizing=False)
        self.menu.grid(row=2,column=0,padx=24,pady=12,sticky='ew')
        self.notice=ct.CTkLabel(self,text='',wraplength=620,justify='left',anchor='w',height=60)
        self.notice.grid(row=3,column=0,padx=24,pady=4,sticky='ew')
        bar=ct.CTkFrame(self,fg_color='transparent');bar.grid(row=4,column=0,padx=24,pady=16,sticky='ew')
        ct.CTkButton(bar,text='刷新窗口',command=self.refresh).pack(side='left')
        ct.CTkButton(bar,text='使用此窗口',command=self.apply).pack(side='right')
        self.refresh();self.after(80,self.lift)
    def refresh(self):
        auto=tr('自动检测');self.choices={}
        try:
            windows=list_windows()
            try:
                chosen=choose_auto(windows);message=tr('自动检测到：')+chosen.title
                auto+=' · '+chosen.title
            except WindowUnavailable as e:
                message=tr(str(e));auto+=' · '+tr('未检测到唯一窗口')
            self.choices[auto]=None
            for w in sorted(windows,key=lambda w:w.title.casefold()):
                label=f'{w.title[:48]} · {w.executable or "PID"} · {w.pid} / {w.hwnd:X}'
                self.choices[label]=w
            self.notice.configure(text=message+'\n'+tr('确认后仅对所选窗口识别；窗口关闭后需重新选择。'))
        except RuntimeError as e:
            self.choices[auto]=None;self.notice.configure(text=tr(str(e)))
        self.menu.configure(values=list(self.choices))
        self.menu.set(next((label for label,w in self.choices.items() if w==self.current),auto))
    def apply(self):
        target=self.choices.get(self.menu.get())
        if target is not None and not valid_target(target):
            self.notice.configure(text='所选窗口已关闭，请重新选择游戏窗口。');return
        self.selected(target);self.destroy()
