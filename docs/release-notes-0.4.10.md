# ColorStudio 0.4.10

## 简体中文

- 界面迁移至 Qt/QML，改善窗口缩放、布局和浮窗体验；修复浮窗点击、拖动、透明度与倒计时更新。
- 修复选色或吸管取色后 HEX 输入框不更新的问题；吸管取色前会隐藏工具并切换到游戏窗口。
- 改善精准寻色的启动读取；修正两种模式中偏离目标后的调整逻辑，减少某一区域改善却让其他区域大幅变差的情况。
- 截图寻色的末尾微调会计入操作、回读与返回所需时间；本轮结束后自动关闭浮窗，也可手动关闭。
- 改善在线更新确认与重启流程，优先使用镜像下载，并校验官方签名和文件完整性。

**安装与更新**

- 首次安装：下载 `ColorStudio-v0.4.10-Windows-x64.zip`，完整解压后运行 `ColorStudio.exe`。
- 已安装用户：在工具中检查更新，下载后安装并重启；设置、方案和记录保留。无法在线更新时，使用完整包手动升级并保留实际使用的 `data` 目录。
- 本版不再提供 UPDATE-ONLY 离线包；发布页的 `blob-` 文件由更新器自动使用，无需手动下载。[更新指南](automatic-updates.md)

**贡献致谢**

- 感谢 **@Marythore** 在 [PR #10](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/10) 中贡献完整 Qt/QML 界面重构；由 **@MinamiChiwa** 在 [PR #11](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/11) 中整合，并继续修复交互、寻色与发布流程。

## 繁體中文

- 介面改用 Qt/QML，改善視窗縮放、版面與浮窗體驗；修正浮窗點擊、拖曳、透明度及倒數更新。
- 修正選色或吸管取色後 HEX 輸入欄未更新的問題；使用吸管前會隱藏工具並切換至遊戲視窗。
- 改善精準尋色的啟動讀取；修正兩種模式偏離目標後的調整邏輯，減少單一區域改善卻讓其他區域明顯變差的情況。
- 截圖尋色末段微調會計入操作、讀回與返回所需時間；本輪結束後自動關閉浮窗，也可手動關閉。
- 改善線上更新確認與重新啟動流程，優先透過鏡像下載，並檢查官方簽章及檔案完整性。

**安裝與更新**

- 首次安裝：下載 `ColorStudio-v0.4.10-Windows-x64.zip`，完整解壓縮後執行 `ColorStudio.exe`。
- 已安裝使用者：在工具中檢查更新，下載後安裝並重新啟動；設定、方案與記錄會保留。無法線上更新時，使用完整包手動升級，並保留實際使用的 `data` 資料夾。
- 本版不再提供 UPDATE-ONLY 離線套件；發布頁的 `blob-` 檔案由更新程式自動使用，不必手動下載。[更新指南](automatic-updates.zh-TW.md)

**貢獻致謝**

- 感謝 **@Marythore** 在 [PR #10](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/10) 貢獻完整 Qt/QML 介面重構；由 **@MinamiChiwa** 在 [PR #11](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/11) 整合，並持續修正互動、尋色與發布流程。

## English

- Moved the interface to Qt/QML, improving window resizing, layout and the overlay. Fixed overlay clicks, dragging, opacity and countdown updates.
- Fixed HEX fields not updating after color selection or eyedropper use. The eyedropper now hides the tool and brings the game window forward before capture.
- Improved Precise Search startup reads. Corrected off-target adjustments in both search modes to reduce improvements in one region at the expense of large regressions in others.
- Screenshot Search now accounts for input, feedback and return time before late adjustments. The overlay closes when the run ends and can also be closed manually.
- Improved update confirmation and restart handling. Downloads prefer a mirror and are checked against the official signature and file hashes.

**Install and update**

- First install: download `ColorStudio-v0.4.10-Windows-x64.zip`, extract the entire archive and run `ColorStudio.exe`.
- Existing users: check for updates in the tool, download, then install and restart. Settings, presets and records are kept. If online updates are unavailable, use the full package and copy your active `data` directory.
- UPDATE-ONLY offline packages are no longer provided. The updater uses the release's `blob-` files automatically; do not download them manually. [Update guide](automatic-updates.en.md)

**Contributors**

- Thanks to **@Marythore** for the complete Qt/QML interface rewrite in [PR #10](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/10). **@MinamiChiwa** integrated it in [PR #11](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/11) and continued the interaction, search and release fixes.

## 日本語

- UI を Qt/QML に移行し、ウィンドウのサイズ変更やレイアウト、フローティングウィンドウの操作を改善しました。クリック・ドラッグ・不透明度・残り時間の表示を修正しました。
- 色の選択やスポイト使用後に HEX 入力欄が更新されない問題を修正しました。スポイト使用時はツールを一時的に隠し、ゲームを前面に表示してから画面を取得します。
- 精密検索の起動時の読み取りを改善しました。両検索モードで目標からずれた際の補正を見直し、ある領域の改善によって他の領域が大きく悪化するケースを減らしました。
- スクリーンショット検索の終了間際の微調整では、操作・再読み取り・戻す操作に必要な時間を考慮します。検索終了時はフローティングウィンドウを閉じ、手動でも閉じられるようにしました。
- 更新の確認と再起動処理を改善しました。ダウンロードはミラーを優先し、公式署名とファイルのハッシュを検証します。

**インストール・更新方法**

- 初回インストール：`ColorStudio-v0.4.10-Windows-x64.zip` をダウンロードし、すべて展開して `ColorStudio.exe` を実行してください。
- インストール済みの場合：ツールで更新を確認・ダウンロードし、インストールして再起動してください。設定・プリセット・履歴は保持されます。オンライン更新が使えない場合は、完全パッケージに現在使用中の `data` フォルダーをコピーして移行できます。
- 今回から UPDATE-ONLY オフラインパッケージは提供しません。公開ファイルの `blob-` は更新プログラムが自動で使用するため、手動ダウンロードは不要です。[更新ガイド](automatic-updates.ja.md)

**貢献者への謝辞**

- [PR #10](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/10) で Qt/QML による全面的な UI 改修を行った **@Marythore** さんに感謝します。**@MinamiChiwa** が [PR #11](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/11) で統合し、操作・検索・リリース処理の修正を続けました。

## 한국어

- UI를 Qt/QML로 전환하고 창 크기 조절, 레이아웃과 플로팅 창 조작을 개선했습니다. 플로팅 창의 클릭·드래그·불투명도·남은 시간 표시를 수정했습니다.
- 색상 선택이나 스포이트 사용 후 HEX 입력란이 갱신되지 않는 문제를 수정했습니다. 스포이트 사용 시 도구를 잠시 숨기고 게임 창을 앞으로 가져온 뒤 화면을 캡처합니다.
- 정밀 검색 시작 시의 읽기 처리를 개선했습니다. 두 검색 모드에서 목표를 벗어난 뒤의 보정 방식을 수정하여, 한 영역이 나아지는 대신 다른 영역의 색상이 크게 나빠지는 경우를 줄였습니다.
- 스크린샷 검색의 마지막 미세 조정에서는 조작·재확인·복귀에 필요한 시간을 고려합니다. 검색이 끝나면 플로팅 창이 닫히며, 직접 닫을 수도 있습니다.
- 업데이트 확인과 재시작 처리를 개선했습니다. 미러를 우선 이용하며 공식 서명과 파일 해시를 검증합니다.

**설치 및 업데이트**

- 첫 설치: `ColorStudio-v0.4.10-Windows-x64.zip`을 다운로드하고 전체 압축을 푼 뒤 `ColorStudio.exe`를 실행하세요.
- 기존 사용자: 도구에서 업데이트를 확인·다운로드한 뒤 설치하고 재시작하세요. 설정·프리셋·기록은 유지됩니다. 온라인 업데이트가 안 되면 전체 패키지로 옮기고 실제 사용 중인 `data` 폴더를 복사하세요.
- 이번 버전부터 UPDATE-ONLY 오프라인 패키지를 제공하지 않습니다. 릴리스의 `blob-` 파일은 업데이트 프로그램이 자동으로 사용하므로 직접 다운로드할 필요가 없습니다. [업데이트 안내](automatic-updates.ko.md)

**기여자 감사**

- [PR #10](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/10)에서 Qt/QML UI 전면 개편을 기여한 **@Marythore** 님께 감사드립니다. **@MinamiChiwa**가 [PR #11](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/pull/11)에서 통합하고 조작·검색·릴리스 관련 수정을 이어 갔습니다.
