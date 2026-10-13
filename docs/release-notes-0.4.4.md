# 0.4.4

## 简体中文

相较0.4.3：

- 改进截图寻色的联合搜索，优先保持两区精准色，并同时寻找符合第三相似色容差的组合。
- 补全候选位置覆盖，减少遗漏；优化亚像素定位和实测微调，保留较好的实测结果。
- 修复小窗口的重复色板识别及备用截图候选取色，避免附近样本与真实终点颜色混淆。
- 精简末尾重复复核，保留必要纠偏与独立达标确认。
- 单区域截图寻色先检查当前视图，每次探索后立即复核，减少无必要的整板采集。
- 修复更新器将已退出工具误判为仍运行、导致安装超时的问题；提供独立更新修复包。
- 完善五语使用提示和说明文档。

更新提示：

- 2026-10-13补修包仍显示0.4.4。已安装早期0.4.4的用户请关闭工具，下载修正版完整包覆盖程序文件并保留 `data`；同版本不会弹出新版本提示。
- 0.4.3及早期0.4.4使用旧安装器时，仍可能在首次更新中超时。若更新已下载且尚未替换文件，关闭工具后解压独立更新修复包，运行 `Recover-Update.cmd`，选择原安装目录即可续装；没有适用的更新记录时，请用完整包并保留 `data`。

多色精准命中不能保证；最终颜色以游戏实际色码为准，是否套用请在游戏内手动决定。支持台服、韩服、日服，韩服和日服仍在测试中。

## 繁體中文

相較0.4.3：

- 改善聯合搜尋，優先保持兩區精準色，並尋找符合第三相似色容差的組合。
- 擴大候選覆蓋範圍，改善細微定位與實測微調，保留較好的實測結果。
- 修復小視窗的重複色板辨識及候選終點取色錯誤。
- 減少結束前的重複複核，保留必要的位置修正與獨立達標確認。
- 單區域每次探索後立即檢查，目標複核達標後停止，減少整板採集。
- 修復更新器將已退出的工具誤判為仍在執行、導致安裝逾時的問題；提供獨立更新修復套件。
- 完善五語使用提示與說明文件。

更新提示：

- 2026-10-13修正版仍顯示0.4.4。已安裝早期0.4.4的使用者請關閉工具，下載修正版完整套件覆蓋程式檔案並保留 `data`；相同版本不會顯示新版本提示。
- 0.4.3與早期0.4.4使用舊更新器時，首次更新仍可能逾時。若更新已下載且尚未替換檔案，關閉工具後解壓縮獨立更新修復套件，執行 `Recover-Update.cmd`，選擇原安裝目錄即可繼續安裝；沒有適用的更新紀錄時，請使用完整套件並保留 `data`。

多色精準命中不保證成功，最終顏色以遊戲實際色碼為準，是否套用請在遊戲內手動決定。支援台服、韓服、日服，韓服與日服仍在測試中。

## English

Changes since 0.4.3:

- Improved joint search for two exact colors and a third color within its Similar tolerance.
- Broader candidate coverage, finer positioning and measured refinement, with the best measured result retained.
- Fixed repeat detection in small windows and incorrect sampling at candidate endpoints.
- Reduced redundant final checks while retaining corrections and independent match confirmation.
- Single-region search checks each view immediately and stops after verifying a match, avoiding unnecessary full-palette capture.
- Fixed update timeouts caused by treating an exited app as still running; added a separate update recovery package.
- Updated guidance and documentation in all five languages.

Update notes:

- The corrected build dated 2026-10-13 still reports 0.4.4. If you installed the earlier 0.4.4, close the app and replace its program files with the corrected full package, keeping `data`. The app does not offer updates with the same version number.
- The first update from 0.4.3 or the earlier 0.4.4 may still time out because it runs the old updater. If the update is downloaded but no files have been replaced, close the app, extract the separate recovery package, run `Recover-Update.cmd` and select the original installation folder. If no suitable pending update exists, use the full package and keep `data`.

Multiple exact matches are not guaranteed. Check the actual game HEX values and apply the result manually. Taiwan, Korean and Japanese servers are supported; Korean and Japanese support remains in testing.

## 日本語

0.4.3からの変更：

- 2部位の完全一致色を優先しながら、3部位目も近似色の許容範囲に収める組み合わせの検索を改善しました。
- 候補の探索範囲、細かい位置合わせ、実測による微調整を改善し、より良い実測結果を保持します。
- 小さいウィンドウでのパレットの繰り返し判定と、候補の移動先の色を誤って評価する問題を修正しました。
- 終了前の重複確認を減らし、必要な位置補正と一致の再確認は維持しました。
- 1部位だけの検索では移動後の画面をすぐに確認し、目標色の一致を確認すると停止します。不要なパレット全体の撮影を省きました。
- 終了済みのアプリを起動中と誤判定し、更新がタイムアウトする問題を修正しました。独立した更新復旧パッケージも用意しました。
- 5言語の案内と説明書を更新しました。

更新について：

- 2026-10-13の修正版もバージョン表示は0.4.4です。初期の0.4.4をお使いの場合はアプリを終了し、修正版の完全パッケージでプログラムファイルを上書きしてください。`data` は残してください。同じバージョン番号の更新通知は表示されません。
- 0.4.3と初期の0.4.4からの最初の更新では、旧更新プログラムが動くためタイムアウトする場合があります。ダウンロード済みでファイルの置き換えが始まっていない場合は、アプリを終了して復旧パッケージを展開し、`Recover-Update.cmd` を実行して元のインストール先を選択してください。利用できる更新記録がない場合は完全パッケージを使い、`data` を残してください。

複数部位の完全一致は保証できません。ゲーム内の実際のHEX値を確認し、結果の適用は手動で判断してください。台湾版・韓国版・日本版に対応していますが、韓国版・日本版の対応はテスト中です。

## 한국어

0.4.3 대비 변경:

- 두 영역의 정확한 색상을 우선 유지하면서 세 번째 영역도 유사 색상 허용 범위에 들어오는 조합을 찾도록 개선했습니다.
- 후보 탐색 범위, 미세한 위치 보정과 실측 미세 조정을 개선하고 더 좋은 실측 결과를 유지합니다.
- 작은 창에서 팔레트 반복을 인식하는 문제와 후보 이동 지점의 색상을 잘못 평가하는 문제를 수정했습니다.
- 마지막 중복 확인을 줄이고 필요한 위치 보정과 독립적인 일치 확인은 유지했습니다.
- 한 영역만 검색할 때는 이동 후 화면을 즉시 확인하고 목표 색상이 확인되면 멈춰, 불필요한 전체 팔레트 수집을 줄입니다.
- 종료된 도구를 실행 중으로 잘못 판단해 업데이트가 시간 초과되는 문제를 수정하고 별도의 업데이트 복구 패키지를 추가했습니다.
- 5개 언어의 안내와 설명서를 정비했습니다.

업데이트 안내:

- 2026-10-13 수정 빌드도 버전은 0.4.4로 표시됩니다. 초기 0.4.4를 설치했다면 도구를 종료하고 수정된 전체 패키지로 프로그램 파일을 덮어쓰되 `data`는 보존해 주세요. 같은 버전 번호의 업데이트 알림은 표시되지 않습니다.
- 0.4.3과 초기 0.4.4는 첫 업데이트에서 기존 업데이트 도구를 사용하므로 시간 초과가 발생할 수 있습니다. 업데이트 다운로드가 끝났지만 파일 교체가 시작되지 않았다면 도구를 종료하고 별도 복구 패키지의 압축을 푼 뒤 `Recover-Update.cmd`를 실행하여 기존 설치 폴더를 선택해 주세요. 사용할 수 있는 업데이트 기록이 없다면 전체 패키지를 사용하고 `data`를 보존해 주세요.

여러 영역의 정확한 일치는 보장하지 않습니다. 게임의 실제 HEX를 확인하고 결과 적용은 직접 결정해 주세요. 대만·한국·일본 서버를 지원하며 한국·일본 서버 지원은 테스트 중입니다.
