# ColorStudio 0.5.0

## 简体中文

- 修复使用寻色浮窗后关闭主窗口仍残留后台进程的问题。
- 精准寻色增加台服、韩服兼容客户端的地址自动发现，减少仅因地址移动而提示版本不支持的情况。
- 自动适配仍需通过布局和当前色板验证；结构变化或验证失败时停止，不保证所有未来更新都兼容。韩服、日服支持状态仍为测试中。
- 截图寻色将长缩放动作分段反馈，按完整路线预留预算，并在无响应或连续无改善时结束定位、微调或恢复，减少末段反复缩放。
- 单区域与多区域改善最佳颜色恢复和状态复用；精准 HEX、区域优先级及实际色码确认条件保持一致。
- 诊断会话按数量保留最近 10 次完成记录，不设 30 天保留期；正在写入或近五分钟更新的会话暂不清理。

**安装与更新**

- 首次安装：下载 `ColorStudio-v0.5.0-Windows-x64.zip`，完整解压后运行 `ColorStudio.exe`。
- 已安装用户：检查更新，下载后安装并重启。手动升级请保留实际使用的 `data` 目录；设置、方案与历史记录和诊断会话的保留规则分别管理。
- 发布页的 `blob-` 文件供更新器使用，无需手动下载。[更新指南](automatic-updates.md)

## 繁體中文

- 修正使用尋色浮窗後關閉主視窗仍殘留背景程序的問題。
- 精準尋色新增台服、韓服相容客戶端的位址自動探索，減少僅因位址移動而顯示版本不支援的情況。
- 自動適配仍須通過結構及目前色板驗證；結構變動或驗證失敗時停止，不保證未來所有更新皆相容。韓服、日服仍在測試中。
- 截圖尋色將長縮放動作分段回饋，依完整路線預留時間，並在無回應或連續未改善時結束定位、微調或恢復，減少末段反覆縮放。
- 單區域與多區域改善最佳顏色恢復及狀態重用；精準 HEX、區域優先順序與實際色碼確認條件維持一致。
- 診斷工作階段保留最近 10 次完成記錄，不設 30 天期限；寫入中或近五分鐘更新的記錄暫不清理。

**安裝與更新**

- 首次安裝：下載 `ColorStudio-v0.5.0-Windows-x64.zip`，完整解壓縮後執行 `ColorStudio.exe`。
- 已安裝使用者：檢查更新，下載後安裝並重新啟動。手動升級請保留實際使用的 `data`；設定、方案、歷史與診斷記錄的保留規則分別管理。
- 發布頁的 `blob-` 檔案由更新程式使用，不必手動下載。[更新指南](automatic-updates.zh-TW.md)

## English

- Fix background processes remaining after closing the main window following use of the search overlay.
- Precise Search can discover addresses for compatible Taiwan and Korean client updates, reducing unsupported-version errors caused solely by moved addresses.
- Discovery still requires layout and current-palette verification. Incompatible changes or failed checks stop the search; future updates are not guaranteed to work. Korean and Japanese support remains in testing.
- Screenshot Search splits long zoom sequences into feedback batches, budgets the complete route, and stops positioning, refinement or recovery when input has no effect or progress stalls, reducing repeated late zoom adjustments.
- Single-region and multi-region searches improve best-color recovery and state reuse. Exact HEX, region priorities and actual-color confirmation requirements remain unchanged.
- Diagnostic storage keeps the latest 10 completed sessions, without a 30-day retention window. Active sessions and sessions updated within five minutes are temporarily protected.

**Install and update**

- First install: download `ColorStudio-v0.5.0-Windows-x64.zip`, extract the entire archive and run `ColorStudio.exe`.
- Existing users: check for updates, download, then install and restart. For manual upgrades, keep your active `data` directory. Settings, presets and history are managed separately from diagnostic-session retention.
- The updater uses the release's `blob-` files automatically; do not download them manually. [Update guide](automatic-updates.en.md)

## 日本語

- 検索フローティングウィンドウの使用後、メイン画面を閉じてもプロセスが残る問題を修正しました。
- 精密検索で互換性のある台湾版・韓国版のアドレスを自動検出し、アドレス移動だけによる未対応エラーを減らします。
- 自動検出後も構造と現在のパレットを検証します。非互換の変更や検証失敗時は停止し、将来のすべての更新への対応は保証しません。韓国版・日本版は引き続きテスト中です。
- スクリーンショット検索の長いズーム操作を分割し、途中で再計測します。経路全体の時間を確保し、無反応や改善の停滞時には位置合わせ・微調整・復元を終了して、終盤の繰り返しズームを減らします。
- 単一部位・複数部位の最良色への復元と状態の再利用を改善しました。完全一致の HEX、部位の優先順位、実際の色コードの確認条件は変更していません。
- 診断ログは完了した直近10回分を保持し、30日間という期限は設けません。書き込み中、または直近5分以内に更新されたログは一時的に保護します。

**インストール・更新方法**

- 初回インストール：`ColorStudio-v0.5.0-Windows-x64.zip` をすべて展開し、`ColorStudio.exe` を実行してください。
- インストール済みの場合：更新を確認・ダウンロードし、インストールして再起動します。手動更新では使用中の `data` を保持してください。設定・プリセット・履歴と診断ログの保持規則は別管理です。
- 公開ファイルの `blob-` は更新プログラム用のため、手動ダウンロードは不要です。[更新ガイド](automatic-updates.ja.md)

## 한국어

- 검색 오버레이 사용 후 메인 창을 닫아도 백그라운드 프로세스가 남는 문제를 수정했습니다.
- 정밀 검색에서 호환되는 대만·한국 클라이언트의 주소를 자동 탐색하여, 주소 이동만으로 발생하는 버전 미지원 오류를 줄입니다.
- 자동 탐색 후에도 구조와 현재 팔레트를 검증합니다. 호환되지 않는 변경이나 검증 실패 시 중지하며, 향후 모든 업데이트의 호환을 보장하지 않습니다. 한국·일본 서버는 계속 테스트 중입니다.
- 스크린샷 검색의 긴 확대·축소 동작을 나누고 중간 결과를 확인합니다. 전체 경로의 시간을 확보하며, 무반응이나 개선 정체 시 위치 보정·미세 조정·복원을 끝내 후반의 반복 확대·축소를 줄입니다.
- 단일·다중 영역의 최적 색상 복원과 상태 재사용을 개선했습니다. 정확한 HEX, 영역 우선순위와 실제 색상 확인 조건은 유지됩니다.
- 진단 로그는 완료된 최근 10회분을 보관하며 30일 보관 기간은 적용하지 않습니다. 쓰는 중이거나 최근 5분 안에 갱신된 로그는 일시적으로 보호합니다.

**설치 및 업데이트**

- 첫 설치: `ColorStudio-v0.5.0-Windows-x64.zip` 전체를 풀고 `ColorStudio.exe`를 실행하세요.
- 기존 사용자: 업데이트 확인·다운로드 후 설치하고 재시작하세요. 수동 업그레이드에서는 실제 사용 중인 `data`를 보관하세요. 설정·프리셋·기록과 진단 로그 보관 규칙은 별도로 관리합니다.
- 릴리스의 `blob-` 파일은 업데이트 프로그램용이므로 직접 다운로드할 필요가 없습니다. [업데이트 안내](automatic-updates.ko.md)
