# 服务器选择 / Server selection

支持台服、韩服、日服；韩服与日服仍在测试中。Supported: Taiwan, Korea and Japan. Korean and Japanese support remains in testing.

[简体中文](../../README.md) · [繁體中文](../../README.zh-TW.md) · [English](../../README.en.md) · [日本語](../../README.ja.md) · [한국어](../../README.ko.md)

简体中文：启动普通 `ColorStudio.exe`，在游戏窗口按钮旁选择台服、韩服或日服，再使用自动检测或选择对应游戏窗口。服务器选择自动保存，切换服务器会清除旧窗口绑定。默认使用精准寻色；无需额外启动器或只读预检。配置目标颜色与优先级，按 F8 开始，看到“寻色已就绪”后进入染色。已经打开染色时也可开始。初次准备和活动色板识别可能需十多秒，浮窗会分别显示阶段，请保持游戏在前台。F7 重试、F9 停止；工具不会自动开启、套用或取消染色。

不要求固定 1280×960，窗口尺寸和 Windows 缩放按本次窗口测量。请先调整游戏窗口再开始；运行中移动或调整窗口后需要按 F8 重新识别，避免继续使用旧坐标。服务选择与窗口标题用于定位，精准流程仍核对 GameAssembly、metadata 与 UnityPlayer 的完整指纹；客户端更新后若版本不匹配，提供日志以更新适配。

韩服上传日志已验证非标准 1376×990 客户区的拖动、双向滚轮及旋转，并得到经过复核的妥协结果。日服按独立指纹、地址与已比对的核心方法接入同一操作流程；实际日服染色响应尚未完成验收。韩服实测不能代替日服实测，也不保证多色精准命中。服务器适配详情见开发仓库同目录下的分析报告。

繁體中文：執行一般 `ColorStudio.exe`，在遊戲視窗按鈕旁選取台服、韓服或日服，再自動偵測或選取對應視窗。選擇會自動儲存，切換伺服器會清除舊視窗綁定。預設使用精準尋色，無需額外啟動器或唯讀預檢。設定目標與優先順序，按 F8 開始，看到「尋色已就緒」後進入染色；已開啟染色時也可開始。初次準備及色板識別可能需十多秒，浮窗會分別顯示階段。保持遊戲在前景；F7 重試、F9 停止，不會自動開啟、套用或取消染色。

無需固定 1280×960，依本次視窗及 Windows 縮放測量。先調整視窗再開始；執行中移動或調整尺寸後，按 F8 重新識別。視窗標題用於定位，精準流程仍核對三個客戶端檔案指紋。韓服已有 1376×990 的操作及實際色碼紀錄；日服已接入共用流程，但實機染色驗收仍待完成。多色精準無法保證成功。

English: Run the normal `ColorStudio.exe`. Select Taiwan, Korea or Japan beside the game-window button, then detect or select the corresponding window. The server choice is saved; switching it clears the old window binding. Precise Search is the default. No separate launcher or read-only preflight is required. Set colors and priorities, press F8, and enter dyeing after the ready message. Starting with dyeing already open is also supported. Initial preparation and active-palette identification can take more than ten seconds; the overlay shows each stage. Keep the game in the foreground. F7 retries and F9 stops. Dyeing is never opened, applied or cancelled automatically.

No fixed 1280×960 resolution is required. Coordinates follow the measured client and Windows scaling. Set the window size before starting; after moving or resizing it during a run, press F8 to identify the current geometry. Window titles guide discovery; Precise Search also verifies the registered GameAssembly, metadata and UnityPlayer fingerprints. Korean records demonstrate drag, zoom, rotation and verified compromise colors at 1376×990. Japan uses its own fingerprint and addresses with the shared workflow; Japanese live dyeing verification remains pending. Multiple exact matches are not guaranteed.

日本語：ゲームウィンドウの横で台湾・韓国・日本のサーバーを選択します。韓国版と日本版の対応はテスト中です。専用の起動スクリプトや事前チェックは不要です。F8 で開始、F7 で再検索（テスト用）、F9 で停止します。結果の適用はゲーム内で手動で行ってください。

한국어: 게임 창 선택 옆에서 대만·한국·일본 서버를 선택하세요. 한국 및 일본 서버 지원은 테스트 중입니다. 별도 실행 스크립트나 사전 점검은 필요하지 않습니다. F8은 시작, F7은 다시 검색(테스트용), F9는 중지입니다. 결과 적용은 게임 내에서 직접 결정하세요.
