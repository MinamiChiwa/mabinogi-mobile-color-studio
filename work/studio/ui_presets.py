"""Named presets with independent editing; current settings autosave separately."""
import tkinter as tk
from tkinter import messagebox
import customtkinter as ct
from display_geometry import logical_size
from profile_store import default_profile, canonical_profile
from ui_typography import TITLE_FONT, BODY_FONT, SMALL_FONT, HEX_FONT
from i18n import tr
import i18n


class PresetDialog(ct.CTkToplevel):
    def __init__(self, parent, store, collect, apply):
        super().__init__(parent)
        self.store=store;self.collect=collect;self.apply=apply;self.selected_id=None
        self.title(tr('染色方案'));self.configure(fg_color='#10151F');self.transient(parent)
        width,height=logical_size(self,(720,690));self.minsize(min(440,width),min(420,height))
        self.geometry(f'{width}x{height}');self.grid_columnconfigure(0,weight=1);self.grid_rowconfigure(2,weight=1)
        ct.CTkLabel(self,text='染色方案',font=TITLE_FONT).grid(row=0,column=0,padx=20,pady=(16,4),sticky='w')
        self.intro=ct.CTkLabel(self,text='当前设置自动保存。这里可命名保存多套方案，也可单独编辑方案。',font=SMALL_FONT,
            wraplength=600,justify='left')
        self.intro.grid(row=1,column=0,padx=20,pady=(0,10),sticky='ew')
        area=ct.CTkScrollableFrame(self,fg_color='transparent');area.grid(row=2,column=0,padx=16,sticky='nsew')
        area.grid_columnconfigure(0,weight=1)
        self.chooser=ct.CTkOptionMenu(area,values=[str(tr('新方案'))],command=self.choose,width=260)
        self.chooser.grid(row=0,column=0,sticky='ew',pady=(0,8))
        self.name=tk.StringVar()
        self.name_entry=ct.CTkEntry(area,textvariable=self.name,placeholder_text='方案名称',font=BODY_FONT)
        self.name_entry.grid(row=1,column=0,sticky='ew',pady=(0,10))
        self.rows=[]
        for i in range(3):
            box=ct.CTkFrame(area,fg_color='#192230');box.grid(row=i+2,column=0,sticky='ew',pady=4)
            box.grid_columnconfigure(1,weight=1)
            enabled=tk.BooleanVar(value=True);target=tk.StringVar();alt=tk.StringVar();tolerance=tk.StringVar(value='8')
            ct.CTkCheckBox(box,text=tr(f'区域 {i+1}'),variable=enabled,font=BODY_FONT,width=90).grid(row=0,column=0,padx=12,pady=10,sticky='w')
            ct.CTkEntry(box,textvariable=target,font=HEX_FONT,placeholder_text='#202020').grid(row=0,column=1,padx=8,pady=10,sticky='ew')
            ct.CTkLabel(box,text='优先级',font=SMALL_FONT).grid(row=1,column=0,padx=12,sticky='w')
            lower=ct.CTkFrame(box,fg_color='transparent');lower.grid(row=1,column=1,padx=8,pady=4,sticky='ew')
            priority=ct.CTkOptionMenu(lower,values=['1','2','3'],width=60,command=lambda value,index=i:self.swap_priority(index,value))
            priority.pack(side='left',padx=(0,8))
            mode=ct.CTkOptionMenu(lower,values=[str(tr('精准 HEX')),str(tr('相似颜色'))],width=120)
            mode.pack(side='left',padx=(0,8))
            ct.CTkEntry(lower,textvariable=tolerance,width=48,font=BODY_FONT).pack(side='left')
            ct.CTkLabel(box,text='替代颜色',font=SMALL_FONT).grid(row=2,column=0,padx=12,pady=(4,10),sticky='w')
            ct.CTkEntry(box,textvariable=alt,placeholder_text='#FFFFFF, #EAEAEA').grid(row=2,column=1,padx=8,pady=(4,10),sticky='ew')
            self.rows.append(dict(enabled=enabled,target=target,alt=alt,tolerance=tolerance,priority=priority,mode=mode))
        self.strategy=ct.CTkOptionMenu(area,values=[str(tr('精准寻色')),str(tr('图像寻色'))],width=240)
        self.strategy.grid(row=5,column=0,sticky='w',pady=8)
        self.priority_note=ct.CTkLabel(area,text='1 为最高优先级；全部区域达标始终优先。',font=SMALL_FONT,wraplength=500,justify='left')
        self.priority_note.grid(row=6,column=0,sticky='ew',pady=(0,8))
        bar=ct.CTkFrame(self,fg_color='transparent');bar.grid(row=3,column=0,padx=16,pady=12,sticky='ew')
        for i in range(2):bar.grid_columnconfigure(i,weight=1)
        self.save_button=ct.CTkButton(bar,text='保存新方案',command=self.save_profile,font=BODY_FONT)
        self.save_button.grid(row=0,column=0,sticky='ew',padx=4,pady=4)
        ct.CTkButton(bar,text='载入到主界面',command=self.load_selected,font=BODY_FONT).grid(row=0,column=1,sticky='ew',padx=4,pady=4)
        ct.CTkButton(bar,text='用当前设置新建',command=self.use_current,font=BODY_FONT,fg_color='#28364A').grid(row=1,column=0,sticky='ew',padx=4,pady=4)
        ct.CTkButton(bar,text='删除方案',command=self.delete_selected,font=BODY_FONT,fg_color='#28364A').grid(row=1,column=1,sticky='ew',padx=4,pady=4)
        self.notice=ct.CTkLabel(self,text='',font=SMALL_FONT,wraplength=600,justify='left')
        self.notice.grid(row=4,column=0,sticky='ew',padx=20,pady=(0,12))
        self._loaded_priorities=[1,2,3]
        self.use_current();self.refresh_language()
        i18n.on_language(self,self.refresh_language)
        self.bind('<Escape>',lambda _:self.destroy())
        self.bind('<Configure>',self.wrap,add='+')
        self.after_idle(lambda:self.geometry(f'{width}x{height}') if self.winfo_exists() else None)

    def wrap(self,event):
        if event.widget is not self:return
        try:width=max(180,int(event.width/self.intro._get_widget_scaling())-48)
        except (AttributeError,tk.TclError):return
        if width==getattr(self,'_wrap_width',None):return
        self._wrap_width=width
        for label in (self.intro,self.notice,self.priority_note):label.configure(wraplength=width)

    def refresh_choices(self):
        try:self.presets=self.store.rows()
        except (ValueError,OSError) as exc:self.presets=[];self.notice.configure(text=tr(str(exc)))
        self.choices={row['name']:row['id'] for row in self.presets}
        self.chooser.configure(values=list(self.choices) or [str(tr('新方案'))])
        current=next((row['name'] for row in self.presets if row['id']==self.selected_id),str(tr('新方案')))
        self.chooser.set(current)

    def refresh_language(self):
        self.name_entry.configure(placeholder_text=str(tr('方案名称')))
        self.mode_values=[str(tr('精准 HEX')),str(tr('相似颜色'))]
        for row in self.rows:
            old=row['mode'].get();exact=old in ('精准 HEX','精準 HEX','Exact HEX')
            row['mode'].configure(values=self.mode_values);row['mode'].set(self.mode_values[0 if exact else 1])
        old=self.strategy.get();native=old in ('精准寻色','精準尋色','Precise Search')
        self.strategy.configure(values=[str(tr('精准寻色')),str(tr('图像寻色'))])
        self.strategy.set(str(tr('精准寻色' if native else '图像寻色')))
        self.refresh_choices()

    def edit(self, profile):
        profile=canonical_profile(profile)
        for i,row in enumerate(self.rows):
            source=profile['regions'][i]
            for key in ('enabled','target','alt'):row[key].set(source[key])
            row['tolerance'].set(f"{source['tolerance']:g}")
            row['mode'].set(str(tr(source['mode'])))
            rank=profile['priority_order'].index(i)+1
            row['priority'].set(str(rank));self._loaded_priorities[i]=rank
        self.strategy.set(str(tr('精准寻色' if profile['search_strategy']=='native' else '图像寻色')))

    def snapshot(self):
        regions=[dict(enabled=row['enabled'].get(),target=row['target'].get(),alt=row['alt'].get(),
            tolerance=float(row['tolerance'].get()),mode='精准 HEX' if row['mode'].get()==str(tr('精准 HEX')) else '相似颜色') for row in self.rows]
        ranks=[int(row['priority'].get()) for row in self.rows]
        if sorted(ranks)!=[1,2,3]:raise ValueError('区域优先级必须包含三个不同区域。')
        return canonical_profile(dict(regions=regions,priority_order=sorted(range(3),key=lambda i:ranks[i]),
            search_strategy='native' if self.strategy.get()==str(tr('精准寻色')) else 'atlas'),strict=True)

    def swap_priority(self,index,value):
        rank=int(value);old=self._loaded_priorities[index]
        for i in range(3):
            if i!=index and self._loaded_priorities[i]==rank:
                self._loaded_priorities[i]=old;self.rows[i]['priority'].set(str(old))
        self._loaded_priorities[index]=rank

    def choose(self,name):
        if name not in self.choices:return
        try:
            self.selected_id=self.choices[name];row=self.store.get(self.selected_id)
            self.name.set(row['name']);self.edit(row['profile']);self.save_button.configure(text='保存修改');self.notice.configure(text='')
        except (ValueError,OSError) as exc:self.notice.configure(text=tr(str(exc)))

    def use_current(self):
        self.selected_id=None;self.name.set('');self.edit(self.collect());self.save_button.configure(text='保存新方案')
        self.chooser.set(str(tr('新方案')));self.notice.configure(text='')

    def save_profile(self):
        try:
            self.selected_id=self.store.save(self.name.get(),self.snapshot(),preset_id=self.selected_id)
            self.refresh_choices();self.save_button.configure(text='保存修改');self.notice.configure(text='方案已保存。')
        except ValueError as exc:self.notice.configure(text=tr(str(exc)) if 'could not convert' not in str(exc) else tr('匹配模式或色差范围无效。'))
        except OSError:self.notice.configure(text=tr('设置未能自动保存，请检查数据目录是否可写。'))

    def load_selected(self):
        try:self.apply(self.snapshot());self.notice.configure(text='方案已载入，当前设置已自动保存。')
        except ValueError as exc:self.notice.configure(text=tr(str(exc)) if 'could not convert' not in str(exc) else tr('匹配模式或色差范围无效。'))
        except OSError:self.notice.configure(text=tr('设置未能自动保存，请检查数据目录是否可写。'))

    def delete_selected(self):
        if self.selected_id is None:return
        if not messagebox.askyesno(tr('删除方案'),tr('确定删除所选方案？'),parent=self):return
        try:self.store.delete(self.selected_id);self.use_current();self.refresh_choices()
        except (ValueError,OSError) as exc:self.notice.configure(text=tr(str(exc)))
