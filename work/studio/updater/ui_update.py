def format_bytes(value):
    value=max(0,int(value));units=('B','KiB','MiB','GiB');number=float(value)
    for unit in units:
        if number<1024 or unit==units[-1]:return f'{number:.1f} {unit}' if unit!='B' else f'{int(number)} B'
        number/=1024

def update_copy(language,version,download_bytes):
    from locale_ja import UPDATE_AVAILABLE_JA
    from locale_ko import UPDATE_AVAILABLE_KO
    size=format_bytes(download_bytes)
    texts={
        '简体中文':(f'有新版本 {version}',f'预计下载 {size}，保留当前设置和染色方案。','下载更新','稍后','忽略此版本','导入离线更新'),
        '繁體中文':(f'有新版本 {version}',f'預計下載 {size}，保留目前設定與染色方案。','下載更新','稍後','忽略此版本','匯入離線更新'),
        'English':(f'Update available: {version}',f'Download: {size}. Your settings and dye presets will be kept.','Download update','Later','Ignore this version','Import offline update'),
        '日本語':tuple(value.format(version=version,size=size) for value in UPDATE_AVAILABLE_JA),
        '한국어':tuple(value.format(version=version,size=size) for value in UPDATE_AVAILABLE_KO),
    }
    title,detail,*buttons=texts.get(language,texts['简体中文'])
    return {'title':title,'detail':detail,'download':buttons[0],'later':buttons[1],'ignore':buttons[2],'offline':buttons[3]}

TEXTS={
 'check':('检查更新','檢查更新','Check for updates'),
 'title':('软件更新','軟體更新','Software update'),
 'checking':('正在检查更新…','正在檢查更新…','Checking for updates…'),
 'none':('当前没有兼容的新版本。','目前沒有相容的新版本。','No compatible update is available.'),
 'network':('无法连接 GitHub。可稍后重试或导入离线更新包。','無法連線至 GitHub。可稍後重試或匯入離線更新包。','Cannot reach GitHub. Retry later or import an offline update.'),
 'busy':('结束当前操作后可更新。','結束目前操作後即可更新。','Finish the current operation before updating.'),
 'ready':('更新已准备好，安装将关闭并重新打开工具。','更新已準備完成，安裝將關閉並重新開啟工具。','Ready to install. The tool will close and reopen.'),
 'install':('安装并重启','安裝並重新啟動','Install and restart'),
 'cancel':('取消下载','取消下載','Cancel download'),
 'cancelled':('下载已暂停，结束当前操作后可继续。','下載已暫停，結束目前操作後可繼續。','Download paused. Resume after the current operation.'),
 'importing':('正在验证离线更新包…','正在驗證離線更新包…','Verifying offline update…'),
 'installing':('正在准备安装，请稍候…','正在準備安裝，請稍候…','Preparing installation…'),
 'trust_unconfigured':('此包未配置正式更新，请使用完整官方安装包。','此套件未設定正式更新，請使用完整官方安裝套件。','Updates are not configured for this package. Use the full official installation package.'),
 'verification':('更新包未能验证，请重新获取官方包。','更新包未能驗證，請重新取得官方套件。','Update verification failed. Obtain the official package again.'),
 'wrong_base':('此离线包不适用于当前文件，请导入完整离线更新包。','此離線套件不適用於目前檔案，請匯入完整離線更新包。','This offline package does not match your files. Import a full offline update.'),
 'conflicts':('程序文件被修改或占用，请保留 data 并使用完整官方包升级。','程式檔案被修改或占用，請保留 data 並使用完整官方套件升級。','Application files were changed or are in use. Keep data and use the full official package.'),
 'manual':('请使用完整安装包手动升级，并保留数据。','請使用完整安裝套件手動升級，並保留資料。','Upgrade manually with the full installation package and keep your data.'),
 'rate_limit':('GitHub 请求已达限制，请稍后重试或使用离线包。','GitHub 請求已達限制，請稍後重試或使用離線套件。','GitHub request limit reached. Retry later or use an offline package.'),
 'automatic':('启动后自动检查','啟動後自動檢查','Check automatically after startup'),
 'prerelease':('允许候选版本','允許候選版本','Include prereleases'),
 'checking_notice':('检查不会下载或安装。更新保留设置、方案和记录。','檢查不會下載或安裝。更新保留設定、方案及紀錄。','Checking does not download or install. Settings, presets and records are kept.'),
 'offline_notice':('离线更新包仅用于已安装的工具，不能首次安装或直接运行。','離線更新套件僅供已安裝的工具使用，不能首次安裝或直接執行。','Offline update packages require an existing installation; they cannot be used for a first install or run directly.'),
}

def text(key,language):
    if language=='日本語':
        from locale_ja import UPDATER_JA
        return UPDATER_JA.get(key,UPDATER_JA['verification'])
    if language=='한국어':
        from locale_ko import UPDATER_KO
        return UPDATER_KO.get(key,UPDATER_KO['verification'])
    return TEXTS.get(key,TEXTS['verification'])[{'简体中文':0,'繁體中文':1,'English':2}.get(language,0)]

class UpdateUI:
    """All widget mutations occur in App's Tk event loop."""
    def __init__(self,app,runtime,parent):
        import customtkinter as ct
        self.app=app;self.runtime=runtime;self.dialog=None;self.last=dict(kind='idle')
        self.button=ct.CTkButton(parent,text=text('check',self.language),width=110,height=32,
            fg_color='#28364A',command=self.open)
        self.button.pack(side='right',padx=4)
    @property
    def language(self):
        import i18n
        return i18n.language
    def open(self):
        import customtkinter as ct
        import tkinter as tk
        from display_geometry import logical_size
        if self.dialog is not None and self.dialog.winfo_exists():self.dialog.lift();return
        self.dialog=win=ct.CTkToplevel(self.app);win.title(text('title',self.language));win.transient(self.app)
        width,height=logical_size(win,(600,450));win.geometry(f'{width}x{height}');win.minsize(min(width,400),min(height,320))
        frame=ct.CTkScrollableFrame(win);frame.pack(fill='both',expand=True,padx=16,pady=16)
        self.heading=ct.CTkLabel(frame,text='',font=('',18,'bold'),wraplength=450,justify='left');self.heading.pack(fill='x',pady=8)
        self.body=ct.CTkLabel(frame,text='',wraplength=450,justify='left');self.body.pack(fill='x',pady=8)
        self.notice=ct.CTkLabel(frame,text=text('checking_notice',self.language),wraplength=450,justify='left');self.notice.pack(fill='x',pady=8)
        self.offline_notice=ct.CTkLabel(frame,text=text('offline_notice',self.language),wraplength=450,justify='left');self.offline_notice.pack(fill='x',pady=8)
        self.automatic=tk.BooleanVar(value=self.runtime.prefs.get('automatic',True))
        self.prerelease=tk.BooleanVar(value=self.runtime.prefs.get('prerelease',False))
        self.auto_button=ct.CTkCheckBox(frame,text=text('automatic',self.language),variable=self.automatic,
            command=lambda:self.runtime.preference(automatic=self.automatic.get()));self.auto_button.pack(anchor='w',pady=6)
        self.pre_button=ct.CTkCheckBox(frame,text=text('prerelease',self.language),variable=self.prerelease,
            command=lambda:self.runtime.preference(prerelease=self.prerelease.get()));self.pre_button.pack(anchor='w',pady=6)
        self.actions={}
        for key,command in (('check',lambda:self.runtime.check(manual=True)),('download',self.runtime.download),
                ('install',self.install),('cancel',self.runtime.cancel),('ignore',self.ignore),('offline',self.offline),('later',win.destroy)):
            button=ct.CTkButton(frame,text=key,command=command);button.pack(fill='x',pady=4);self.actions[key]=button
        self.refresh()
    def install(self):
        self.runtime.set_busy(self.operation_busy())
        if self.runtime.service.busy:self.handle(dict(kind='blocked',reason='busy'));return
        if not self.app.flush_autosave():return
        self.runtime.install()
    def operation_busy(self):
        return (self.app.busy or self.app.picking or self.app.__dict__.get('_window_selecting',False)
            or self.app.__dict__.get('_color_selecting',False))
    def ignore(self):
        manifest=self.runtime.service.manifest
        if manifest is not None:self.runtime.preference(ignored=manifest.version)
        if self.dialog is not None:self.dialog.destroy()
        self.button.configure(text=text('check',self.language))
    def offline(self):
        from tkinter import filedialog
        path=filedialog.askopenfilename(parent=self.dialog,title=text('title',self.language),filetypes=[('ZIP','*.zip')])
        if path:self.runtime.offline(path)
    def handle(self,event):
        import time
        if event['kind']=='download':
            now=time.monotonic()
            if self.last.get('kind')!='download':self._download_origin=(now,event['received'])
            origin=self._download_origin
            event=dict(event,speed=max(0.,(event['received']-origin[1])/max(.01,now-origin[0])))
        self.last=event
        if event['kind']=='exit_requested':
            self.app._update_install_exit=True;self.app.close();return
        self.refresh()
    def refresh(self):
        event=self.last;kind=event['kind'];version=event.get('version') or getattr(self.runtime.service.manifest,'version','')
        copy=update_copy(self.language,version,event.get('download_bytes',getattr(self.runtime.service.plan,'download_bytes',0)))
        self.button.configure(text=copy['title'] if version and self.runtime.service.state in ('available','ready') else text('check',self.language))
        if self.dialog is None or not self.dialog.winfo_exists():return
        self.dialog.title(text('title',self.language));self.notice.configure(text=text('checking_notice',self.language))
        self.offline_notice.configure(text=text('offline_notice',self.language))
        self.auto_button.configure(text=text('automatic',self.language));self.pre_button.configure(text=text('prerelease',self.language))
        self.heading.configure(text=copy['title'] if version else text('title',self.language))
        body=copy['detail'] if kind=='available' else text('checking_notice' if kind=='idle' else kind if kind in TEXTS else ('manual' if event.get('reason')=='bootstrap_required' else event.get('reason','verification')),self.language)
        if kind=='download':body=f"{format_bytes(event['received'])} / {format_bytes(event['total'])} · {format_bytes(event.get('speed',0))}/s"
        if event.get('conflicts'):body+='\n'+text('conflicts',self.language)
        self.body.configure(text=body)
        for key,button in self.actions.items():
            button.configure(text=copy.get(key,text(key,self.language)))
            enabled=(key in ('later','offline','check') or key=='download' and self.runtime.service.state=='available'
                or key=='install' and self.runtime.service.state=='ready' or key=='cancel' and self.runtime.service.state in ('checking','downloading')
                or key=='ignore' and bool(version))
            if key in ('offline','download','install') and self.operation_busy():enabled=False
            button.configure(state='normal' if enabled else 'disabled')
