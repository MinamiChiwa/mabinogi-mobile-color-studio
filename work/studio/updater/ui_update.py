"""Five-language updater copy; the Qt update dialog renders it."""


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
        '简体中文':(f'有新版本 {version}',f'预计下载 {size}，保留当前设置和染色方案。','下载更新','稍后','忽略此版本'),
        '繁體中文':(f'有新版本 {version}',f'預計下載 {size}，保留目前設定與染色方案。','下載更新','稍後','忽略此版本'),
        'English':(f'Update available: {version}',f'Download: {size}. Your settings and dye presets will be kept.','Download update','Later','Ignore this version'),
        '日本語':tuple(value.format(version=version,size=size) for value in UPDATE_AVAILABLE_JA),
        '한국어':tuple(value.format(version=version,size=size) for value in UPDATE_AVAILABLE_KO),
    }
    title,detail,*buttons=texts.get(language,texts['简体中文'])
    return {'title':title,'detail':detail,'download':buttons[0],'later':buttons[1],'ignore':buttons[2]}

TEXTS={
 'check':('检查更新','檢查更新','Check for updates'),
 'title':('软件更新','軟體更新','Software update'),
 'checking':('正在检查更新…','正在檢查更新…','Checking for updates…'),
 'none':('当前没有兼容的新版本。','目前沒有相容的新版本。','No compatible update is available.'),
 'network':('无法连接更新服务器（镜像与 GitHub 均不可用），请稍后重试。','無法連線至更新伺服器（鏡像與 GitHub 皆無法使用），請稍後再試。','Cannot reach the update server (mirror and GitHub both unavailable). Retry later.'),
 'busy':('结束当前操作后可更新。','結束目前操作後即可更新。','Finish the current operation before updating.'),
 'ready':('更新已准备好，安装将关闭并重新打开工具。','更新已準備完成，安裝將關閉並重新開啟工具。','Ready to install. The tool will close and reopen.'),
 'install':('安装并重启','安裝並重新啟動','Install and restart'),
 'cancel':('取消下载','取消下載','Cancel download'),
 'cancelled':('下载已暂停，结束当前操作后可继续。','下載已暫停，結束目前操作後可繼續。','Download paused. Resume after the current operation.'),
 'installing':('正在准备安装，请稍候…','正在準備安裝，請稍候…','Preparing installation…'),
 'trust_unconfigured':('此包未配置正式更新，请使用完整官方安装包。','此套件未設定正式更新，請使用完整官方安裝套件。','Updates are not configured for this package. Use the full official installation package.'),
 'verification':('更新包未能验证，请重新获取官方包。','更新包未能驗證，請重新取得官方套件。','Update verification failed. Obtain the official package again.'),
 'conflicts':('程序文件被修改或占用，请保留 data 并使用完整官方包升级。','程式檔案被修改或占用，請保留 data 並使用完整官方套件升級。','Application files were changed or are in use. Keep data and use the full official package.'),
 'manual':('请使用完整安装包手动升级，并保留数据。','請使用完整安裝套件手動升級，並保留資料。','Upgrade manually with the full installation package and keep your data.'),
 'rate_limit':('GitHub 请求已达限制，请稍后重试。','GitHub 請求已達限制，請稍後再試。','GitHub request limit reached. Retry later.'),
 'automatic':('启动后自动检查','啟動後自動檢查','Check automatically after startup'),
 'prerelease':('允许候选版本','允許候選版本','Include prereleases'),
 'checking_notice':('检查不会下载或安装。更新保留设置、方案和记录。','檢查不會下載或安裝。更新保留設定、方案及紀錄。','Checking does not download or install. Settings, presets and records are kept.'),
}

def text(key,language):
    if language=='日本語':
        from locale_ja import UPDATER_JA
        return UPDATER_JA.get(key,UPDATER_JA['verification'])
    if language=='한국어':
        from locale_ko import UPDATER_KO
        return UPDATER_KO.get(key,UPDATER_KO['verification'])
    return TEXTS.get(key,TEXTS['verification'])[{'简体中文':0,'繁體中文':1,'English':2}.get(language,0)]
