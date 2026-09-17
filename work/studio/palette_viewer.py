"""Scrollable one-page full-color atlas with pixel-accurate inspection."""
import tkinter as tk
import time
from i18n import tr
import customtkinter as ct
from PIL import Image,ImageTk
from palette import full_atlas

class PaletteViewer(ct.CTkToplevel):
    def __init__(self,parent,colors,target,pool):
        super().__init__(parent);self.title(tr('允许颜色 · 完整色图'));self.configure(fg_color='#10151F')
        self.geometry(f'{min(1000,self.winfo_screenwidth()-100)}x{min(740,self.winfo_screenheight()-100)}+40+40')
        self.image=None;self.scale=1.;self.target=target;self.transient(parent)
        self._render_job=None;self._item=None;self._last_inspect=0.;self._last_color=None
        top=ct.CTkFrame(self,fg_color='transparent');top.pack(fill='x',padx=20,pady=(16,8))
        ct.CTkLabel(top,text=f'{target} · {len(colors):,} 种允许颜色',font=('Microsoft YaHei UI',18,'bold')).pack(side='left')
        for label,fn in [('适合窗口',self.fit),('原始尺寸',lambda:self.render(1)),('＋',lambda:self.render(self.scale*2)),('－',lambda:self.render(self.scale/2))]:
            ct.CTkButton(top,text=label,width=78,command=fn).pack(side='right',padx=3)
        self.note=ct.CTkLabel(self,text='正在生成完整色图…',anchor='w');self.note.pack(fill='x',padx=20,pady=(0,8))
        frame=tk.Frame(self,bg='#192230');frame.pack(fill='both',expand=True,padx=20,pady=(0,20))
        frame.grid_rowconfigure(0,weight=1);frame.grid_columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(frame,bg='#192230',highlightthickness=0)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        xs=tk.Scrollbar(frame,orient='horizontal',command=self.canvas.xview);xs.grid(row=1,column=0,sticky='ew')
        ys=tk.Scrollbar(frame,orient='vertical',command=self.canvas.yview);ys.grid(row=0,column=1,sticky='ns')
        self.canvas.configure(xscrollcommand=xs.set,yscrollcommand=ys.set)
        self.canvas.bind('<Motion>',self.inspect)
        self.canvas.bind('<MouseWheel>',lambda e:'break')
        self.canvas.bind('<ButtonPress-1>',lambda e:self.canvas.scan_mark(e.x,e.y))
        self.canvas.bind('<B1-Motion>',lambda e:self.canvas.scan_dragto(e.x,e.y,gain=1))
        self.bind('<Escape>',lambda e:self.destroy())
        self.future=pool.submit(full_atlas,colors.copy());self.after(100,self.poll)
    def poll(self):
        if not self.winfo_exists():return
        if not self.future.done():self.after(100,self.poll);return
        try:self.image=self.future.result();self.fit()
        except Exception:self.note.configure(text='色图生成失败，请关闭后重试。')
    def fit(self):
        if self.image is not None:
            self.update_idletasks();self.render(min(self.canvas.winfo_width()/self.image.width,self.canvas.winfo_height()/self.image.height))
    def render(self,scale):
        if self.image is None:return
        # Bound Tk bitmap memory while allowing every source pixel to be seen.
        self.scale=max(.1,min(scale,8,6000/max(self.image.size)))
        if self._render_job is None:self._render_job=self.after(16,self._render)
    def _render(self):
        self._render_job=None
        size=tuple(max(1,round(s*self.scale)) for s in self.image.size)
        self.photo=ImageTk.PhotoImage(self.image.resize(size,Image.Resampling.NEAREST),master=self)
        if self._item is None:self._item=self.canvas.create_image(0,0,image=self.photo,anchor='nw')
        else:self.canvas.itemconfigure(self._item,image=self.photo)
        self.canvas.configure(scrollregion=(0,0,*size));self._last_color=None
        self.note.configure(text=f'{self.scale:.0%} · 色差由中心向外增加 · 放大查看每个颜色，拖动或滚动浏览，悬停查看 HEX')
    def inspect(self,event):
        if self.image is None:return
        now=time.monotonic()
        if now-self._last_inspect<.033:return
        self._last_inspect=now
        x=int(self.canvas.canvasx(event.x)/self.scale);y=int(self.canvas.canvasy(event.y)/self.scale)
        if 0<=x<self.image.width and 0<=y<self.image.height:
            color='#%02X%02X%02X'%self.image.getpixel((x,y))
            if color==self._last_color:return
            self._last_color=color
            self.note.configure(text=f'{self.scale:.0%} · 当前色块 {color} · 拖动浏览 / ＋ 放大 / － 缩小')
