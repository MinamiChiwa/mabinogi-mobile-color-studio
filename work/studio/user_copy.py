"""Reviewed user-facing copy; source values and runtime identifiers stay unchanged."""

# Each row: English, Traditional Chinese, Japanese, Korean.
ROWS = {
  "自动操作已停止": [
    "Automatic input stopped",
    "自動操作已停止",
    "自動操作を停止しました",
    "자동 조작 중지"
  ],
  "请在游戏中查看当前颜色，并手动决定是否套用。": [
    "Check the current colors in the game and decide whether to apply them.",
    "請在遊戲中查看目前顏色，並手動決定是否套用。",
    "ゲーム内で現在の色を確認し、適用するか決めてください。",
    "게임에서 현재 색상을 확인하고 적용 여부를 결정하세요."
  ],
  "1. 选择服务器与窗口": [
    "1. Select the server and window",
    "1. 選擇伺服器與視窗",
    "1. サーバーとウィンドウを選ぶ",
    "1. 서버와 창 선택"
  ],
  "选择台服、韩服或日服，再选择游戏窗口。窗口位置和大小请在开始前调整。": [
    "Select Taiwan, Korea or Japan, then choose the game window. Adjust its position and size before starting.",
    "選擇台服、韓服或日服，再選擇遊戲視窗。請在開始前調整視窗位置與大小。",
    "台湾・韓国・日本を選び、ゲームウィンドウを指定します。位置とサイズは開始前に調整してください。",
    "대만·한국·일본 서버와 게임 창을 선택하세요. 창 위치와 크기는 시작 전에 조정하세요."
  ],
  "2. 设置颜色要求": [
    "2. Set matching requirements",
    "2. 設定顏色要求",
    "2. 色の一致条件を設定する",
    "2. 색상 일치 조건 설정"
  ],
  "启用需要匹配的区域并设置目标色。精准 HEX 要求六位色码一致；相似颜色按设定色差匹配。优先级 1 最高。": [
    "Enable the regions and choose target colors. Exact HEX requires the same six-digit code; Similar uses your tolerance. Priority 1 is highest.",
    "啟用要比對的區域並設定目標色。精準 HEX 要求六位色碼一致；相似顏色依設定色差比對。優先順序 1 最高。",
    "対象部位を有効にして目標色を設定します。完全一致（HEX）は6桁のコード一致、近似色は許容色差で検索します。優先順位1が最優先です。",
    "영역을 켜고 목표 색상을 설정하세요. 완전 일치(HEX)는 6자리 코드 일치, 유사 색상은 설정한 허용 색차로 검색합니다. 우선순위 1이 가장 높습니다."
  ],
  "3. 选择寻色方式": [
    "3. Choose a search method",
    "3. 選擇尋色方式",
    "3. 検索方式を選ぶ",
    "3. 검색 방식 선택"
  ],
  "截图寻色是默认方式，使用截图与鼠标操作。精准寻色会读取游戏内存，风险较高；它与颜色要求中的精准 HEX 是不同设置。": [
    "Screenshot Search is the default and uses images and mouse input. Precise Search reads game memory and carries higher risk. It is separate from the Exact HEX matching requirement.",
    "截圖尋色是預設方式，使用截圖與滑鼠操作。精準尋色會讀取遊戲記憶體，風險較高；它與顏色要求中的精準 HEX 是不同設定。",
    "標準のスクリーンショット検索は画像とマウス操作を使います。精密検索はゲームのメモリを読み取り、リスクが高くなります。色の一致条件である完全一致（HEX）とは別の設定です。",
    "기본인 스크린샷 검색은 이미지와 마우스 조작을 사용합니다. 정밀 검색은 게임 메모리를 읽어 위험이 더 높습니다. 색상 조건의 완전 일치(HEX)와는 다른 설정입니다."
  ],
  "4. 开始寻色": [
    "4. Start searching",
    "4. 開始尋色",
    "4. 検索を開始する",
    "4. 검색 시작"
  ],
  "按 F8 或点击开始，按提示进入染色；色板已打开时也可启动。自动操作期间保持游戏在前台，避免移动鼠标或改变窗口。": [
    "Press F8 or Start and follow the prompt to open dyeing. You can start with the palette already open. Keep the game in front and avoid moving the mouse or changing its window during automatic input.",
    "按 F8 或點選開始，依提示進入染色；色板已開啟時也可啟動。自動操作時保持遊戲在前景，避免移動滑鼠或改變視窗。",
    "F8または開始を押し、案内に従って染色画面を開きます。パレットを開いた後でも開始できます。自動操作中はゲームを最前面にし、マウス操作やウィンドウ変更を避けてください。",
    "F8 또는 시작을 누르고 안내에 따라 염색 화면을 여세요. 팔레트를 연 뒤 시작해도 됩니다. 자동 조작 중에는 게임을 맨 앞에 두고 마우스 조작이나 창 변경을 피하세요."
  ],
  "5. 查看结果": [
    "5. Review the result",
    "5. 查看結果",
    "5. 結果を確認する",
    "5. 결과 확인"
  ],
  "查看各区域的游戏实际色码与色差，再决定是否套用。标为上次实测的颜色是历史记录，请查看游戏当前画面。": [
    "Review each region's actual game HEX and color difference before applying. Last measured colors are earlier readings; check the current game view.",
    "查看各區域的遊戲實際色碼與色差，再決定是否套用。標為上次實測的顏色是歷史紀錄，請查看遊戲目前畫面。",
    "各部位の実際のカラーコードと色差を確認してから適用を決めます。前回の実測は過去の読み取り値です。現在のゲーム画面を確認してください。",
    "영역별 실제 게임 색상 코드와 색차를 확인한 뒤 적용 여부를 결정하세요. 마지막 실측 색상은 이전 기록이므로 현재 게임 화면을 확인하세요."
  ],
  "6. 停止或重试": [
    "6. Stop or retry",
    "6. 停止或重試",
    "6. 停止・再検索",
    "6. 중지 또는 재검색"
  ],
  "F9 停止自动操作。F7 重新寻色（仅供测试）：缩小色板后继续本局搜索，沿用剩余时间，不额外使用染色剂。": [
    "F9 stops automatic input. F7 retries (Testing only): zoom out and search again with this round's remaining time, without another dye item.",
    "F9 停止自動操作。F7 重新尋色（僅供測試）：縮小色板後繼續本局搜尋，沿用剩餘時間，不額外使用染色劑。",
    "F9で自動操作を停止します。F7は再検索（テスト用）です。パレットを縮小して同じ染色の残り時間で検索し直し、追加の染色アイテムは使いません。",
    "F9로 자동 조작을 중지합니다. F7 재검색(테스트용)은 팔레트를 축소한 뒤 같은 회차의 남은 시간으로 다시 검색하며 염색 아이템을 추가로 쓰지 않습니다."
  ],
  "设置自动保存": [
    "Settings save automatically",
    "設定自動儲存",
    "設定の自動保存",
    "설정 자동 저장"
  ],
  "颜色、匹配要求和优先级自动保存。保存方案可保留多套命名设置；编辑后载入即可使用。": [
    "Colors, matching requirements and priorities save automatically. Save preset keeps named settings; load an edited preset to use it.",
    "顏色、比對要求及優先順序會自動儲存。儲存方案可保留多套命名設定；編輯後載入即可使用。",
    "色、一致条件、優先順位は自動保存されます。プリセット保存で複数の設定に名前を付けられます。編集後は読み込んで使用してください。",
    "색상, 일치 조건, 우선순위는 자동 저장됩니다. 프리셋 저장으로 여러 설정에 이름을 붙일 수 있으며 편집 후 불러오면 사용할 수 있습니다."
  ],
  "正在优化当前配色": [
    "Looking for a better combination",
    "正在改善目前配色",
    "より良い配色を検索中",
    "더 나은 조합 검색 중"
  ],
  "正在计算更好的配色，计算期间色板可能暂时不动。": [
    "Calculating a better combination. The palette may remain still during this stage.",
    "正在計算更好的配色，計算時色板可能暫時不動。",
    "より良い配色を計算しています。この間はパレットが動かないことがあります。",
    "더 나은 조합을 계산하고 있습니다. 이 단계에서는 팔레트가 잠시 움직이지 않을 수 있습니다."
  ],
  "可查看下方已确认的颜色；满意时按 F9 停止。": [
    "Review the verified colors below. Press F9 to stop when satisfied.",
    "可查看下方已確認的顏色；滿意時按 F9 停止。",
    "下に表示した確認済みの色をご覧ください。満足できたらF9で停止できます。",
    "아래 확인된 색상을 보세요. 만족하면 F9로 중지하세요."
  ],
  "正在准备寻色，请保持游戏窗口可见。F9 可停止。": [
    "Preparing search. Keep the game window visible. F9 stops.",
    "正在準備尋色，請保持遊戲視窗可見。F9 可停止。",
    "検索を準備しています。ゲームウィンドウを表示したままにしてください。F9で停止できます。",
    "검색을 준비하고 있습니다. 게임 창을 보이는 상태로 두세요. F9로 중지할 수 있습니다."
  ],
  "请按提示进入染色；已经打开色板时无需重新进入。F9 可停止。": [
    "Follow the prompt to open dyeing. If the palette is already open, keep it open. F9 stops.",
    "請依提示進入染色；色板已開啟時不必重新進入。F9 可停止。",
    "案内に従って染色画面を開いてください。パレットが開いていればそのままで構いません。F9で停止できます。",
    "안내에 따라 염색 화면을 여세요. 이미 팔레트가 열려 있으면 그대로 두세요. F9로 중지할 수 있습니다."
  ],
  "正在计算目标位置，色板暂时不动。F9 可停止。": [
    "Calculating target positions; the palette remains still. F9 stops.",
    "正在計算目標位置，色板暫時不動。F9 可停止。",
    "目標位置を計算しています。パレットは一時的に動きません。F9で停止できます。",
    "목표 위치를 계산하고 있어 팔레트가 잠시 움직이지 않습니다. F9로 중지할 수 있습니다."
  ],
  "正在调整色板，请保持游戏在前台。F9 可停止。": [
    "Adjusting the palette. Keep the game in front. F9 stops.",
    "正在調整色板，請保持遊戲在前景。F9 可停止。",
    "パレットを調整しています。ゲームを最前面に保ってください。F9で停止できます。",
    "팔레트를 조정하고 있습니다. 게임을 맨 앞에 두세요. F9로 중지할 수 있습니다."
  ],
  "正在尝试返回本轮最好颜色": [
    "Trying to return to the best measured colors",
    "正在嘗試回到本局最佳實測顏色",
    "今回の最良実測色への復帰を試行中",
    "이번 회차의 최선 실측 색상으로 복귀 시도 중"
  ],
  "正在按游戏画面调整位置。F9 可停止。": [
    "Adjusting the position using the game view. F9 stops.",
    "正在依遊戲畫面調整位置。F9 可停止。",
    "ゲーム画面を確認しながら位置を調整しています。F9で停止できます。",
    "게임 화면을 확인하며 위치를 조정하고 있습니다. F9로 중지할 수 있습니다."
  ],
  "正在寻找目标颜色。可按 F9 停止，再查看游戏当前结果。": [
    "Searching for target colors. Press F9 to stop and review the current game result.",
    "正在尋找目標顏色。可按 F9 停止，再查看遊戲目前結果。",
    "目標色を検索しています。F9で停止して現在のゲーム結果を確認できます。",
    "목표 색상을 검색하고 있습니다. F9로 중지하고 현재 게임 결과를 확인할 수 있습니다."
  ],
  "查看各区域的实测色码与色差，再在游戏内决定是否套用。": [
    "Review each region's measured HEX and color difference, then decide whether to apply in the game.",
    "查看各區域的實測色碼與色差，再於遊戲內決定是否套用。",
    "各部位の実測カラーコードと色差を確認し、ゲーム内で適用を決めてください。",
    "영역별 실측 색상 코드와 색차를 확인하고 게임에서 적용 여부를 결정하세요."
  ],
  "程序不会自动套用；请在游戏内手动确认。": [
    "The tool does not apply colors automatically. Confirm manually in the game.",
    "程式不會自動套用；請在遊戲內手動確認。",
    "ツールは自動で適用しません。ゲーム内で手動で確認してください。",
    "도구는 자동 적용하지 않습니다. 게임에서 직접 확인하세요."
  ],
  "请使用完整安装包手动升级，并保留数据。": [
    "Upgrade manually with the full installation package and keep your data.",
    "請使用完整安裝套件手動升級，並保留資料。",
    "完全インストールパッケージで手動更新し、データを引き継いでください。",
    "전체 설치 패키지로 수동 업그레이드하고 데이터를 유지하세요."
  ],
  "此包未配置正式更新，请使用完整官方安装包。": [
    "Updates are not configured for this package. Use the full official installation package.",
    "此套件未設定正式更新，請使用完整官方安裝套件。",
    "このパッケージは正式更新が設定されていません。公式の完全インストールパッケージを使ってください。",
    "이 패키지에는 공식 업데이트가 설정되지 않았습니다. 공식 전체 설치 패키지를 사용하세요."
  ],
  "离线更新包仅用于已安装的工具，不能首次安装或直接运行。": [
    "Offline update packages require an existing installation; they cannot be used for a first install or run directly.",
    "離線更新套件僅供已安裝的工具使用，不能首次安裝或直接執行。",
    "オフライン更新パッケージはインストール済みのツール用です。初回インストールや直接実行には使えません。",
    "오프라인 업데이트 패키지는 기존 도구용입니다. 첫 설치나 직접 실행에는 사용할 수 없습니다."
  ],
  "支持台服；韩服和日服测试中。": [
    "Taiwan supported; Korea and Japan in testing.",
    "支援台服；韓服與日服測試中。",
    "台湾版対応・韓国版と日本版はテスト中。",
    "대만 서버 지원 · 한국·일본 서버 테스트 중."
  ],
  "颜色要求": [
    "Matching requirement",
    "顏色要求",
    "一致条件",
    "일치 조건"
  ],
  "寻色方式": [
    "Search method",
    "尋色方式",
    "検索方式",
    "검색 방식"
  ],
  "寻色方式：截图寻色。不读取游戏内存。": [
    "Search method: Screenshot Search. No game memory reads.",
    "尋色方式：截圖尋色。不讀取遊戲記憶體。",
    "検索方式：スクリーンショット検索。ゲームのメモリは読み取りません。",
    "검색 방식: 스크린샷 검색. 게임 메모리를 읽지 않습니다."
  ],
  "寻色方式：精准寻色。会读取游戏内存，风险较高。": [
    "Search method: Precise Search. Reads game memory; higher risk.",
    "尋色方式：精準尋色。會讀取遊戲記憶體，風險較高。",
    "検索方式：精密検索。ゲームのメモリを読み取るため、リスクが高くなります。",
    "검색 방식: 정밀 검색. 게임 메모리를 읽어 위험이 더 높습니다."
  ],
  "颜色要求：六位 HEX 必须一致": [
    "Matching requirement: identical six-digit HEX",
    "顏色要求：六位 HEX 必須一致",
    "一致条件：6桁のHEXが一致",
    "일치 조건: 6자리 HEX 일치"
  ],
  "颜色要求：色差 ΔE ≤ ": [
    "Matching requirement: difference ΔE ≤ ",
    "顏色要求：色差 ΔE ≤ ",
    "一致条件：色差 ΔE ≤ ",
    "일치 조건: 색차 ΔE ≤ "
  ],
  " · 越小越接近目标": [
    " · Lower means closer",
    " · 越小越接近目標",
    " · 小さいほど目標に近い色",
    " · 작을수록 목표에 가까움"
  ],
  "自动操作已停止。请查看游戏当前颜色。": [
    "Automatic input stopped. Check the current game colors.",
    "自動操作已停止。請查看遊戲目前顏色。",
    "自動操作を停止しました。ゲーム内の現在の色を確認してください。",
    "자동 조작을 중지했습니다. 게임의 현재 색상을 확인하세요."
  ]
}

EN = {source: values[0] for source, values in ROWS.items()}
TW = {source: values[1] for source, values in ROWS.items()}
JA = {source: values[2] for source, values in ROWS.items()}
KO = {source: values[3] for source, values in ROWS.items()}
