"""Resizable information dialogs. Links open only on an explicit button click."""
import webbrowser
import customtkinter as ct
from ui_typography import TITLE_FONT,SECTION_FONT,BODY_FONT
from display_geometry import logical_size

GITHUB='https://github.com/MinamiChiwa/mabinogi-mobile-color-studio'
AFDIAN='https://afdian.com/a/minamichiwa'
PATREON='https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink'
TUTORIAL=[
('1. 设置游戏窗口','在游戏中依次打开【图形】→【畫面設定】→【視窗模式】→【解析度】，设为 1280 × 960。'),
('2. 选择游戏窗口','在本工具左上角选择正在运行游戏的窗口；只有一个游戏窗口时也可以使用自动检测。'),
('3. 设置目标颜色','设置需要固定的颜色，并启用对应染色区域。可输入 HEX 色码、点击选色，或使用屏幕吸管。'),
('4. 选择匹配模式','为每个区域选择精准或相似模式。'),
('5. 启动后再进入染色','按 F8 或点击开始。待浮窗出现后，再手动打开游戏内染色倒计时界面；识别成功后程序自动开始。'),
('6. 自动操作期间','请尽量不要操作鼠标，保持游戏在前台，不要移动或缩放游戏窗口。按 F9 可随时停止；是否使用染色结果，请在游戏内手动确认。'),
('Tips 1 · 匹配方式','精准模式要求 HEX 完全一致；相似模式使用设定的色差范围。妥协方案优先保持各区域色系，再优先减小精准区域色差。'),
('Tips 2 · 等待与候选','工具先拼接本局色板，再搜索并定位；浮窗会显示进度。想改选其他方案，请尽早点击候选卡。倒计时不足以安全移动和复核时，程序会保持当前方案。'),
('结果与问题反馈','自动染色并非完美，最终色差可能较大。如结果未达到预期，可重新开始一局。遇到问题请到 GitHub 提交 Issue，并附上本次日志。'),
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
