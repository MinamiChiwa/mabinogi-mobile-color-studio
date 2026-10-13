"""Resizable information dialogs. Links open only on an explicit button click."""
import webbrowser
import customtkinter as ct
from ui_typography import TITLE_FONT,SECTION_FONT,BODY_FONT
from display_geometry import logical_size

GITHUB='https://github.com/MinamiChiwa/mabinogi-mobile-color-studio'
AFDIAN='https://afdian.com/a/minamichiwa'
PATREON='https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink'
TUTORIAL=[
('1. 选择服务器与游戏窗口','在左上角选择台服、韩服或日服，再选择游戏窗口；窗口检测与服务器联动，无需固定分辨率或额外预检。'),
('2. 设置目标颜色','启用需要染色的区域，输入 HEX 色码、点击选色或使用屏幕吸管。替代颜色同样视为可接受的目标。工具自动识别双区域或三区域色板；本局不存在的区域不参与匹配，保存的设置仍会保留。'),
('3. 选择匹配模式','精准 HEX 要求六位色码完全一致；相似颜色按各区域设置的 ΔE 色差范围匹配。'),
('4. 设置区域优先级','1 为最高优先级，全部区域达标始终优先。需要妥协时，按优先级依次比较是否达标和色差；低优先级的精准命中不会压过高优先级的大幅改善。相似模式中，区域进入设定容差后优先改善后续区域。调整一个区域会自动交换另一区域的优先级。'),
('5. 开始寻色','按 F8 或点击开始，等待提示后手动进入游戏染色界面。也可在已经进入染色界面后启动工具。默认使用截图寻色，通过原始截图搜索并核对实际色码。'),
('6. 自动操作期间','保持游戏在前台，尽量不要操作鼠标，也不要移动或调整游戏窗口。按 F9 可随时停止。程序不会自动开启染色、套用或确认结果，请在游戏内自行决定。'),
('Tips 1 · 寻色与结果','截图寻色采集原始颜色，规划平移、缩放与旋转，并核对游戏色码。未全部达标时尽量保留按优先级排序的最佳实测妥协结果；浮窗只显示实测状态，不显示预测候选。'),
('Tips 2 · 材质限制','游戏内皮革、木材等材质的基础色不含纯黑或纯白时，无法精准抓取 #000000 或 #FFFFFF。请以游戏实际显示的色码为准。'),
('Tips 3 · 多色精准','多个区域共享色板的平移、缩放与旋转，目标组合不一定同时可达。多色精准抓取不能保证成功率；请检查妥协结果的各区域色差后再决定是否使用。'),
('截图寻色说明','截图寻色会缩小和放大采集颜色，再计算移动、旋转与缩放。精确目标和相似目标均以游戏实际 HEX 复核；没有命中时展示实测妥协结果，不能保证多个区域精准成功。可按 F7 使用本局已有截图重搜，F9 停止并保留当前游戏画面。'),
('Tips 4 · 自动保存与方案','颜色、区域开关、匹配模式和优先级会自动保存，下次启动恢复。点击保存方案可命名保存多套配置，也可编辑、载入或删除方案。'),
('Tips 5 · 本局重试','点击浮窗「重新寻色」或按 F7，可结束当前搜索，向下滚轮缩小画板至最大可见范围后重新搜索。重试沿用本局剩余时间，不消耗新道具；时间不足时保留当前颜色。F9 停止全部操作。'),
('结果与问题反馈','最终结果以游戏当前色码为准。遇到问题请在 GitHub 提交 Issue，并附上本次日志；不要为了反馈反复消耗染色道具。'),
('使用风险','截图寻色使用截图和鼠标操作，不读取游戏内存，风险相对较低。精准寻色读取游戏内存，风险较高，可能触发游戏检测或账号处罚。截图方式也不保证账号安全，请自行评估是否使用。'),
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
