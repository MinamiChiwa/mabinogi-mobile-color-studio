"""Resizable information dialogs. Links open only on an explicit button click."""
import webbrowser
import customtkinter as ct
from ui_typography import TITLE_FONT,SECTION_FONT,BODY_FONT
from display_geometry import logical_size

GITHUB='https://github.com/MinamiChiwa/mabinogi-mobile-color-studio'
AFDIAN='https://afdian.com/a/minamichiwa'
PATREON='https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink'
TUTORIAL=[
('1. 选择服务器与窗口','选择台服、韩服或日服，再选择游戏窗口。窗口位置和大小请在开始前调整。'),
('2. 设置颜色要求','启用需要匹配的区域并设置目标色。精准 HEX 要求六位色码一致；相似颜色按设定色差匹配。优先级 1 最高。'),
('3. 选择寻色方式','截图寻色是默认方式，使用截图与鼠标操作。精准寻色会读取游戏内存，风险较高；它与颜色要求中的精准 HEX 是不同设置。'),
('4. 开始寻色','按 F8 或点击开始，按提示进入染色；色板已打开时也可启动。自动操作期间保持游戏在前台，避免移动鼠标或改变窗口。'),
('5. 查看结果','查看各区域的游戏实际色码与色差，再决定是否套用。标为上次实测的颜色是历史记录，请查看游戏当前画面。'),
('6. 停止或重试','F9 停止自动操作。F7 重新寻色（仅供测试）：缩小色板后继续本局搜索，沿用剩余时间，不额外使用染色剂。'),
('设置自动保存','颜色、匹配要求和优先级自动保存。保存方案可保留多套命名设置；编辑后载入即可使用。'),
]


def logical_screen_limit(window, preferred, margins=(80, 100)):
    """Return a logical CTk size that fits the native physical screen.

    CustomTkinter scales geometry width/height by the OS window scale while
    ``winfo_screenwidth/height`` are native pixels in this DPI-aware process.
    """
    return logical_size(window,preferred,margins)


class InfoDialog(ct.CTkToplevel):
    def __init__(self,parent,title,sections,links=(),size=(660,650)):
        super().__init__(parent)
        self.title(title);self.configure(fg_color='#10151F');self.transient(parent)
        width,height=logical_screen_limit(self,size)
        # Keep the minimum in logical units so CTk does not create a window
        # larger than a small high-DPI display can show.
        self.minsize(min(440,width),min(330,height));self.grid_columnconfigure(0,weight=1);self.grid_rowconfigure(1,weight=1)
        # CTkToplevel applies minsize to the native window; set the requested
        # geometry afterward so the window manager does not keep its 200x200
        # bootstrap size.
        self.geometry(f'{width}x{height}')
        ct.CTkLabel(self,text=title,font=TITLE_FONT).grid(row=0,column=0,padx=24,pady=(20,12),sticky='w')
        self.area=ct.CTkScrollableFrame(self,fg_color='transparent');self.area.grid(row=1,column=0,padx=16,sticky='nsew')
        self.labels=[]
        for heading,body in sections:
            box=ct.CTkFrame(self.area,fg_color='#192230');box.pack(fill='x',pady=5)
            for text,font,color in ((heading,SECTION_FONT,'#62D7BD'),(body,BODY_FONT,'#EDF3FA')):
                if not text:continue
                label=ct.CTkLabel(box,text=text,font=font,text_color=color,wraplength=560,justify='left',anchor='w')
                label.pack(fill='x',padx=16,pady=8);self.labels.append(label)
        bar=ct.CTkFrame(self,fg_color='transparent');bar.grid(row=2,column=0,padx=20,pady=16,sticky='ew')
        for index,(name,url) in enumerate(links):
            bar.grid_columnconfigure(index,weight=1)
            ct.CTkButton(bar,text=name,width=90,font=BODY_FONT,command=lambda u=url:webbrowser.open(u)).grid(row=0,column=index,sticky='ew',padx=4,pady=(0,10))
        ct.CTkButton(bar,text='关闭',font=BODY_FONT,fg_color='#28364A',command=self.destroy).grid(row=1,column=0,columnspan=max(1,len(links)),sticky='ew',padx=4)
        self._resize_job=None;self._wrap_width=0
        self.bind('<Configure>',self.schedule_wrap,add='+')
        self.bind('<Escape>',lambda _:self.destroy());self.after(80,self.lift)
        self.after_idle(lambda:self.geometry(f'{width}x{height}') if self.winfo_exists() else None)
    def schedule_wrap(self,event):
        if event.widget!=self:return
        if self._resize_job:self.after_cancel(self._resize_job)
        self._resize_job=self.after(80,self.wrap)
    def wrap(self):
        self._resize_job=None
        width=max(100,int(self.winfo_width()/self.area._get_widget_scaling())-100)
        if abs(width-self._wrap_width)<8:return
        self._wrap_width=width
        for label in self.labels:label.configure(wraplength=width)


def support_dialog(parent):
    return InfoDialog(parent,'支持作者',[
        ('','赞助完全自愿，不论是否赞助，都可以正常使用本工具的全部功能。'),
        ('','选择您偏好的平台支持后续开发，感谢您的支持。')],
        [('爱发电',AFDIAN),('Patreon',PATREON)],size=(590,440))


def tutorial_dialog(parent):
    return InfoDialog(parent,'使用教程',TUTORIAL,[('提交问题 / Issues',GITHUB+'/issues')])
