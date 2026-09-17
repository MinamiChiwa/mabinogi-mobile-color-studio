import platform_win  # Set physical-pixel awareness before Tk or capture initializes.
import customtkinter as ct
import tkinter as tk
from tkinter import colorchooser,messagebox
from pathlib import Path
import sys,json,threading,queue,datetime,ctypes,webbrowser
from engine import Runner
import i18n
from i18n import tr
from vision import normalize_hex
from palette import allowed_colors,overview
from palette_viewer import PaletteViewer
from result_history import describe_result,read_history,save_result
from eyedropper import pick_screen
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from vision import rgb
PALETTE_POOL=ThreadPoolExecutor(max_workers=1)
from PIL import Image,ImageDraw

ct.set_appearance_mode('dark'); ct.set_default_color_theme('blue')
BG='#10151F'; PANEL='#192230'; INK='#EDF3FA'; MUTED='#94A4B8'; ACCENT='#62D7BD'
FONT='Microsoft YaHei UI'
DATA=Path(__file__).resolve().parent/'data' if not getattr(sys,'frozen',False) else Path(sys.executable).parent/'data'
DATA.mkdir(exist_ok=True)
try:i18n.language=json.loads((DATA/'settings.json').read_text(encoding='utf-8')).get('language','简体中文')
except (OSError,ValueError):pass
i18n.install_widgets(ct)

class Card(ct.CTkFrame):
    def __init__(self,parent,index):
        super().__init__(parent,fg_color=PANEL,corner_radius=18,border_width=1,border_color='#2A3546')
        self.index=index; self.enabled=tk.BooleanVar(value=index==0); self.mode=tk.StringVar(value='精准 HEX'); self.tolerance=tk.DoubleVar(value=8)
        self.target=tk.StringVar(value='#202020'); self.alt=tk.StringVar(value='')
        self.grid_columnconfigure(0,weight=1)
        ct.CTkLabel(self,text=f'0{index+1}  /  颜色区域',font=(FONT,16,'bold'),text_color=INK,height=22).grid(row=0,column=0,padx=20,pady=(14,8),sticky='w')
        ct.CTkSwitch(self,text='匹配此区域',variable=self.enabled,font=(FONT,12),progress_color=ACCENT).grid(row=1,column=0,padx=20,sticky='w')
        self.preview_frame=ct.CTkFrame(self,fg_color='transparent')
        self.preview_frame.grid(row=2,column=0,padx=20,pady=(8,6),sticky='ew')
        self.swatch=ct.CTkButton(self.preview_frame,text='点击选色',height=34,corner_radius=10,command=self.pick,font=(FONT,13),fg_color='#202020',hover_color='#35445B')
        self.swatch.pack(fill='x')
        ct.CTkButton(self.preview_frame,text='⌖  屏幕吸管',height=26,fg_color='#28364A',hover_color='#364D63',font=(FONT,11),command=lambda:pick_screen(self.winfo_toplevel(),self.target.set)).pack(fill='x',pady=(5,0))
        self.palette=ct.CTkLabel(self.preview_frame,text='',height=64)
        self.palette.pack(fill='x',pady=(6,0))
        self.palette.bind('<Button-1>',self.open_palette)
        self.palette.configure(cursor='hand2')
        self.palette_note=ct.CTkLabel(self.preview_frame,text='目标色集合',font=(FONT,10),text_color=MUTED,height=14)
        self.palette_note.pack(anchor='w')
        self._palette_future=None;self._palette_key=None;self._palette_pixels=None
        self._preview_job=None
        ct.CTkEntry(self,textvariable=self.target,height=36,font=('Consolas',16),border_color='#36445B').grid(row=3,column=0,padx=20,sticky='ew')
        ct.CTkLabel(self,text='替代颜色 · 多个颜色用逗号分隔',font=(FONT,11),text_color=MUTED,height=20).grid(row=4,column=0,padx=20,pady=(8,4),sticky='w')
        ct.CTkEntry(self,textvariable=self.alt,height=34,placeholder_text='#FFFFFF, #EAEAEA').grid(row=5,column=0,padx=20,sticky='ew')
        self.alts=ct.CTkFrame(self,fg_color='transparent',height=18); self.alts.grid(row=6,column=0,padx=20,pady=3,sticky='ew');self.alts.pack_propagate(False)
        ct.CTkSegmentedButton(self,values=['精准 HEX','相似颜色'],variable=self.mode,command=self.change_mode,font=(FONT,12),selected_color='#236D62',selected_hover_color='#2C8275').grid(row=7,column=0,padx=20,pady=(8,10),sticky='ew')
        self.slider=ct.CTkSlider(self,from_=1,to=35,number_of_steps=34,variable=self.tolerance,command=self.change_mode,progress_color=ACCENT,button_color=ACCENT)
        self.slider.grid(row=8,column=0,padx=20,sticky='ew')
        self.hint=ct.CTkLabel(self,text='',font=(FONT,11),text_color=MUTED,height=20);self.hint.grid(row=9,column=0,padx=20,pady=(0,6),sticky='w')
        self.current=ct.CTkLabel(self,text='当前颜色  —',font=(FONT,12),text_color=MUTED,height=20);self.current.grid(row=10,column=0,padx=20,pady=(0,10),sticky='w')
        self.best_label=ct.CTkLabel(self,text='最佳结果  —',font=(FONT,11),text_color=ACCENT,height=22,corner_radius=5);self.best_label.grid(row=11,column=0,padx=20,pady=(0,8),sticky='ew')
        self.target.trace_add('write',self.preview);self.alt.trace_add('write',self.preview); self.preview();self.change_mode()
    def change_mode(self,*_):
        exact=self.mode.get()=='精准 HEX'; self.slider.configure(state='disabled' if exact else 'normal',progress_color='#45505F' if exact else ACCENT,button_color='#596273' if exact else ACCENT,button_hover_color='#596273' if exact else '#80E5CF',fg_color='#303947' if exact else '#3A485D')
        self.hint.configure(text='六位色码必须完全一致' if exact else f'感知色差 ΔE ≤ {self.tolerance.get():.0f} · 数值越小越严格')
        self.schedule_palette()
    def preview(self,*_):
        try:
            v=normalize_hex(self.target.get()); self.swatch.configure(fg_color=v,text_color='#17202B' if sum(int(v[i:i+2],16) for i in (1,3,5))>430 else 'white')
        except ValueError:pass
        for child in self.alts.winfo_children():child.destroy()
        for part in self.alt.get().replace('，',',').split(',')[:6]:
            try:ct.CTkLabel(self.alts,text='',width=20,height=18,corner_radius=4,fg_color=normalize_hex(part)).pack(side='left',padx=(0,5))
            except ValueError:pass
        self.schedule_palette()
    def schedule_palette(self):
        if self._preview_job:self.after_cancel(self._preview_job)
        self._preview_job=self.after(80,self.draw_palette)
    def draw_palette(self):
        self._preview_job=None
        try:target=normalize_hex(self.target.get())
        except ValueError:
            self.palette.configure(image=None,text='请输入有效 HEX');self.palette_note.configure(text='颜色未设置完整');return
        exact=self.mode.get()=='精准 HEX'
        key=(target,0 if exact else float(self.tolerance.get()))
        self._palette_key=key
        if self._palette_future:self._palette_future.cancel()
        if exact:
            self._palette_pixels=np.array([rgb(target)],np.uint8);self.render_palette();return
        self.palette.configure(image=None,text='正在计算允许的颜色…')
        self.palette_note.configure(text='正在准备颜色预览…')
        future=PALETTE_POOL.submit(allowed_colors,*key);self._palette_future=future
        self.after(100,lambda:self.poll_palette(future,key))
    def poll_palette(self,future,key):
        if key!=self._palette_key or future is not self._palette_future:return
        if not future.done():self.after(100,lambda:self.poll_palette(future,key));return
        try:self._palette_pixels=future.result()
        except Exception:self.palette_note.configure(text='预览计算失败，请重新选择颜色');return
        self.render_palette()
    def render_palette(self):
        im=overview(self._palette_pixels)
        new_image=ct.CTkImage(light_image=im,dark_image=im,size=(240,64))
        self.palette.configure(image=new_image,text='')
        self.palette_image=new_image
        count=len(self._palette_pixels)
        note=f'目标色集合 · {count:,} 色'
        note+=' · 点击查看全部'
        self.palette_note.configure(text=note)
    def open_palette(self,event=None):
        if self._palette_pixels is not None and self._palette_key:
            PaletteViewer(self.winfo_toplevel(),self._palette_pixels,self._palette_key[0],PALETTE_POOL)
    def pick(self):
        v=colorchooser.askcolor(parent=self,title=tr(f'区域 {self.index+1} · 选择目标颜色'))[1]
        if v:self.target.set(v.upper())
    def rule(self):
        if not self.enabled.get():return {'enabled':False,'colors':[],'exact':True,'tolerance':0}
        colors=[normalize_hex(self.target.get())]+[normalize_hex(x) for x in self.alt.get().replace('，',',').split(',') if x.strip()]
        return {'enabled':True,'colors':colors,'exact':self.mode.get()=='精准 HEX','tolerance':self.tolerance.get()}

class App(ct.CTk):
    def __init__(self):
        super().__init__();self.title(tr('染色工坊 · 瑪奇 Mobile'));self.geometry('1060x900');self.minsize(960,740);self.configure(fg_color=BG)
        self.after(100,self.fit_screen)
        self.active_rules=None;self.history=read_history(DATA/'history.json');self.best_summary=None
        self.q=queue.Queue();self.runner=None;self.busy=False;self.picking=False;self.keys={};self.cards=[];self.auto=tk.BooleanVar(value=False)
        self.grid_columnconfigure(0,weight=1); self.grid_rowconfigure(2,weight=1)
        header=ct.CTkFrame(self,fg_color='transparent');header.grid(row=0,column=0,padx=32,pady=(24,8),sticky='ew')
        ct.CTkLabel(header,text='染色工坊',font=(FONT,28,'bold'),text_color=INK).pack(side='left')
        ct.CTkLabel(header,text='瑪奇 Mobile  /  by 南千和',font=(FONT,12),text_color=MUTED).pack(side='left',padx=18,pady=(10,0))
        ct.CTkOptionMenu(header,values=['简体中文','繁體中文','English'],width=115,command=self.change_language,variable=tk.StringVar(value=i18n.language)).pack(side='right',padx=(8,0))
        ct.CTkButton(header,text='保存方案',width=90,height=32,fg_color='#28364A',command=self.save).pack(side='right')
        ct.CTkButton(header,text='♥  支持作者',width=110,height=32,fg_color='#694C91',hover_color='#8260AE',command=lambda:webbrowser.open('https://afdian.com/a/minamichiwa')).pack(side='right',padx=8)
        ct.CTkButton(header,text='寻色记录',width=90,height=32,fg_color='#28364A',command=self.show_history).pack(side='right')
        intro=ct.CTkFrame(self,fg_color='transparent');intro.grid(row=1,column=0,padx=32,pady=(0,10),sticky='ew')
        ct.CTkLabel(intro,text='① 设置目标颜色    →    ② 游戏内打开普通染色    →    ③ 教学结束后按 F8',font=(FONT,13),text_color=MUTED).pack(anchor='w')
        ct.CTkLabel(intro,text='精准色更难寻找  ·  推荐从相似模式 ΔE 8–12 开始，数值越小越接近目标',font=(FONT,13,'bold'),text_color='#FFD18A',fg_color='#342C22',corner_radius=8,height=34).pack(fill='x',pady=(6,0))
        body=ct.CTkFrame(self,fg_color='transparent');body.grid(row=2,column=0,padx=24,sticky='nsew');body.grid_rowconfigure(0,weight=1)
        for i in range(3):
            body.grid_columnconfigure(i,weight=1,uniform='cards');card=Card(body,i);card.grid(row=0,column=i,padx=8,sticky='nsew');self.cards.append(card)
        controls=ct.CTkFrame(self,fg_color='transparent');controls.grid(row=3,column=0,padx=32,pady=(18,8),sticky='ew')
        self.start=ct.CTkButton(controls,text='开始寻色   F8',height=44,width=165,font=(FONT,14,'bold'),fg_color=ACCENT,text_color='#102A27',hover_color='#80E5CF',command=self.go);self.start.pack(side='left')
        ct.CTkButton(controls,text='停止   F9',height=44,width=100,fg_color='#2B384C',command=self.stop).pack(side='left',padx=10)
        ct.CTkCheckBox(controls,text='达标后自动复核并套用',variable=self.auto,font=(FONT,12),fg_color='#236D62').pack(side='left',padx=12)
        ct.CTkButton(controls,text='诊断',width=65,height=34,fg_color='#28364A',command=self.diagnostics).pack(side='right')
        ct.CTkButton(controls,text='取当前色 F7',width=100,height=34,fg_color='#28364A',command=lambda:self.go('capture')).pack(side='right',padx=8)
        status=ct.CTkFrame(self,fg_color=PANEL,corner_radius=14);status.grid(row=4,column=0,padx=32,pady=(8,10),sticky='ew');status.grid_columnconfigure(0,weight=1)
        self.status=ct.CTkLabel(status,text='就绪 · 支持横屏与竖屏识别',font=(FONT,14),anchor='w',wraplength=920,text_color=INK);self.status.grid(row=0,column=0,padx=18,pady=(12,5),sticky='ew')
        self.detail=ct.CTkLabel(status,text='持续寻找更接近的颜色，剩余约 30 秒返回本轮最佳组合，由你确认是否使用。',font=(FONT,11),text_color=MUTED,wraplength=920,anchor='w');self.detail.grid(row=1,column=0,padx=18,pady=(0,12),sticky='ew')
        ct.CTkLabel(intro,text='适用于港澳台服瑪奇Mobile。游戏中使用本程序存在风险，请自行斟酌。',font=(FONT,11),text_color=MUTED,wraplength=940).pack(fill='x',pady=(3,0))
        ct.CTkLabel(self,text='F9 随时停止并释放鼠标  ·  切换窗口停止寻色  ·  不自动开启下一瓶染色剂',font=(FONT,11),text_color=MUTED).grid(row=5,column=0,pady=(0,14))
        self.load()
        if self.history:self.display_best(self.history[0])
        threading.Thread(target=self.hotkey_loop,daemon=True).start()
        self.after(30,self.tick);self.protocol('WM_DELETE_WINDOW',self.close)
    def change_language(self,value):
        if self.busy:
            self.status.configure(text=tr('请先停止寻色再切换语言。'));return
        self.save()
        (DATA/'settings.json').write_text(json.dumps({'language':value},ensure_ascii=False),encoding='utf-8')
        import subprocess
        args=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve())]
        self.destroy();subprocess.Popen(args)
        __import__('os')._exit(0)
    def display_best(self,row):
        self.best_summary=row
        for c,r in zip(self.cards,row['regions']):
            delta=r['delta'];color=r['color']
            text=f'{color or "—"} · ΔE {delta:.2f}' if delta is not None else f'{color or "—"} · 未参与匹配'
            c.best_label.configure(text=text,fg_color=color or '#28364A',text_color='#17202B' if color and sum(rgb(color))>430 else 'white')
        if row['maximum'] is not None:
            self.detail.configure(text=f'{"本次结果" if row.get("outcome") else "最佳组合"} · 最大色差 ΔE {row["maximum"]:.2f} / 平均 {row["average"]:.2f} · 色差越小越接近目标')
    def show_history(self):
        win=ct.CTkToplevel(self);win.title(tr('寻色记录 · by 南千和'));win.geometry('820x620');win.transient(self);win.configure(fg_color=BG)
        ct.CTkLabel(win,text='寻色记录',font=(FONT,24,'bold')).pack(anchor='w',padx=24,pady=(20,4))
        ct.CTkLabel(win,text='记录最近 50 次结果 · ΔE 越小越接近目标，0 表示目标原色',text_color=MUTED).pack(anchor='w',padx=24,pady=(0,12))
        area=ct.CTkScrollableFrame(win,fg_color=BG);area.pack(fill='both',expand=True,padx=16,pady=(0,16))
        if not self.history:ct.CTkLabel(area,text='完成一次寻色后，颜色组合会自动保存在这里。').pack(pady=40)
        names={'matched':'目标达标','compromise':'妥协结果','applied':'已套用'}
        for row in self.history:
            box=ct.CTkFrame(area,fg_color=PANEL,corner_radius=12);box.pack(fill='x',pady=6)
            title=f'{row["time"]}  ·  {names.get(row.get("outcome"),"寻色结果")}'
            if row['maximum'] is not None:title+=f'  ·  最大 ΔE {row["maximum"]:.2f} / 平均 {row["average"]:.2f}'
            ct.CTkLabel(box,text=title,anchor='w').pack(fill='x',padx=12,pady=(8,4))
            line=ct.CTkFrame(box,fg_color='transparent');line.pack(fill='x',padx=12,pady=(0,10))
            for r in row['regions']:
                color=r['color'];delta=r['delta'];text=f'区域 {r["region"]}  {color or "未识别"}'
                text+=f'\n色差 ΔE {delta:.2f}' if delta is not None else '\n未参与匹配'
                ct.CTkLabel(line,text=text,width=205,height=52,corner_radius=8,fg_color=color or '#28364A',text_color='#17202B' if color and sum(rgb(color))>430 else 'white').pack(side='left',expand=True,fill='x',padx=3)
    def diagnostics(self):
        if messagebox.askyesno(tr('输入诊断'),tr('请先进入游戏限时染色界面。\n将依次测试左键平移、右键圆弧和滚轮缩放，记录前后色码与截图，不套用结果。\n\n是否开始？'),parent=self):self.go('diagnostic')
    def fit_screen(self):
        # Keep footer and emergency controls inside the monitor work area at high DPI.
        scale=self._get_window_scaling()
        h=min(900,int((self.winfo_screenheight()-85)/scale))
        if h<900:ct.set_widget_scaling(max(.65,h/900));ct.set_window_scaling(max(.65,h/900));h=900
        self.geometry(f'1060x{h}+40+30')
    def save(self):
        try:
            data=[{'enabled':c.enabled.get(),'target':c.target.get(),'alt':c.alt.get(),'mode':c.mode.get(),'tolerance':c.tolerance.get()} for c in self.cards]
            for c in self.cards:c.rule()
            (DATA/'profile.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');self.status.configure(text='方案已保存，下次启动自动恢复。')
        except Exception as e:self.status.configure(text=str(e))
    def load(self):
        try:
            for c,d in zip(self.cards,json.loads((DATA/'profile.json').read_text(encoding='utf-8'))):
                for key in ['enabled','target','alt','mode','tolerance']:getattr(c,key).set(d[key])
                c.change_mode()
        except (OSError,ValueError,KeyError):pass
    def go(self,mode='search'):
        if self.busy or self.picking:return
        try:
            rules=[c.rule() for c in self.cards]
            if mode=='search' and not any(r['enabled'] for r in rules):raise ValueError('请至少启用一个颜色区域。')
        except ValueError as e:self.status.configure(text=str(e));return
        self.active_rules=rules
        self.busy=True;self.start.configure(state='disabled');self.status.configure(text='正在识别游戏界面…')
        folder=DATA/'sessions'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        self.runner=Runner(lambda k,d:self.q.put((k,d)),folder)
        threading.Thread(target=self.runner.launch,args=(rules,mode,self.auto.get()),daemon=True).start()
    def stop(self):
        if self.runner:self.runner.stop.set();self.status.configure(text='正在停止并释放鼠标…')
    def hotkey_loop(self):
        registered=[]
        keys=[(1,0x77),(2,0x78),(3,0x79),(4,0x76)]
        if not getattr(sys,'frozen',False):keys.append((5,0x75)) # Development-only controlled recovery test.
        for i,vk in keys:
            if platform_win.u.RegisterHotKey(None,i,0x4000,vk):registered.append(i)
            else:self.q.put(('error',{'message':'快捷键被其他程序占用，请使用界面按钮。'}))
        msg=platform_win.W.MSG()
        while platform_win.u.GetMessageW(ctypes.byref(msg),None,0,0)>0:
            if msg.message==0x312:self.q.put(('hotkey',{'id':int(msg.wParam)}))
    def tick(self):
        while not self.q.empty():
            k,d=self.q.get()
            if k=='hotkey':
                if d['id']==1:self.go()
                elif d['id']==2:self.stop()
                elif d['id']==3:self.go('diagnostic')
                elif d['id']==4:self.go('capture')
                elif d['id']==5:self.go('recovery_test')
            elif k=='targets':
                for c,color in zip(self.cards,d['colors']):
                    c.enabled.set(True);c.target.set(color);c.alt.set('')
                self.save()
            elif k in ('scene','match','restore_action'):
                for i,(c,color) in enumerate(zip(self.cards,d.get('colors',[]))):
                    inactive=self.active_rules is not None and not self.active_rules[i]['enabled']
                    c.current.configure(text='当前颜色  '+(color or ('未参与匹配' if inactive else '读取失败')))
                if k=='scene':self.status.configure(text=f'正在寻色 · 游戏剩余 {d.get("seconds") or "—"} 秒')
                elif k=='restore_action':self.status.configure(text=f'正在恢复最佳颜色 · 游戏剩余 {d.get("seconds") or "—"} 秒')
            elif k=='action':self.detail.configure(text='正在调整色板，持续寻找更接近的颜色…')
            elif k in ('explore','restoring','magnifying'):self.detail.configure(text=d['message'])
            elif k=='best':
                if self.active_rules:self.display_best(describe_result(d['colors'],self.active_rules))
            elif k in ('error','done'):
                self.status.configure(text=d.get('message',''))
                for c,color in zip(self.cards,d.get('colors',[])):c.current.configure(text='当前颜色  '+(color or '读取失败'))
                if d.get('popup'):
                    if self.active_rules:
                        try:
                            row=save_result(DATA/'history.json',d.get('colors',[]),self.active_rules,d.get('outcome'),d.get('restored'),d.get('best_colors'))
                            self.history=read_history(DATA/'history.json');self.display_best(row)
                        except OSError:self.detail.configure(text='本轮结果未能保存，请检查程序文件夹是否可写。')
                    message=d['message']+'\n\n当前颜色：'+' / '.join(c or '未识别' for c in d.get('colors',[]))
                    self.after(100,lambda m=message,o=d.get('outcome'):messagebox.showinfo(tr('流程完成 · '+('妥协结果' if o=='compromise' else '目标达标')),tr(m),parent=self))
            elif k=='finished':self.busy=False;self.start.configure(state='normal')
        self.after(60,self.tick)
    def close(self):
        if self.busy:self.stop();self.after(250,self.close)
        else:
            for i in (1,2,3,4,5):platform_win.u.UnregisterHotKey(None,i)
            self.destroy()

if __name__=='__main__':App().mainloop()
