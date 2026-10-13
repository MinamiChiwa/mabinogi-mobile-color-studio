# 0.4.4

相较0.4.3：

- 改进截图寻色的联合搜索，优先保持两区精准色，并同时寻找符合第三相似色容差的组合。
- 补全候选位置覆盖，减少遗漏；优化亚像素定位和实测微调，保留较好的实测结果。
- 修复小窗口的重复色板识别及备用截图候选取色，避免附近样本与真实终点颜色混淆。
- 精简末尾重复复核，保留必要纠偏与独立达标确认。
- 单区域截图寻色先检查当前视图，每次探索后立即复核，减少无必要的整板采集。
- 完善五语使用提示和说明文档。

多色精准命中不能保证；最终颜色以游戏实际色码为准，是否套用请在游戏内手动决定。支持台服、韩服、日服，韩服和日服仍在测试中。

## 繁體中文

相較0.4.3：改善截圖尋色的聯合搜尋，優先保持兩區精準色，並尋找符合第三相似色容差的組合。補全候選位置、改善細微定位與實測微調，精簡結束前的重複複核。單區域先檢查目前畫面，每次探索後立即複核，找到目標就停止，減少不必要的整板採集。完善五語提示與文件。多色精準命中不保證成功，是否套用請在遊戲內手動決定。韓服與日服仍在測試中。

## English

Changes since 0.4.3: improved screenshot search for two exact colors and one similar color, broader candidate coverage, subpixel positioning and measured refinement, and fewer redundant final checks. Single-region search checks each view immediately and stops after verifying a match, avoiding unnecessary full-palette capture. Five-language guidance has also been updated. Multiple exact matches are not guaranteed; confirm application manually in-game. Korean and Japanese support remains in testing.

## 日本語

0.4.3からの変更：スクリーンショット検索で2部位の完全一致色と1部位の近似色を同時に探す処理を改善しました。候補位置の探索範囲、細かい位置合わせ、実測による微調整を改善し、終了前の重複確認を削減しました。1部位だけの検索では表示中の範囲をすぐに確認し、目標色の一致を確認すると停止します。不要なパレット全体の撮影を省きました。5言語の案内と説明書も更新しています。複数部位の完全一致は保証できません。結果の適用はゲーム内で手動で判断してください。韓国版・日本版の対応はテスト中です。

## 한국어

0.4.3 대비 변경: 스크린샷 검색에서 두 영역의 정확한 색상과 한 영역의 유사 색상을 함께 찾는 과정을 개선했습니다. 후보 위치 탐색, 미세한 위치 보정과 실측 미세 조정을 개선하고 마지막 중복 확인을 줄였습니다. 한 영역만 검색할 때는 현재 화면과 이동 후 화면을 즉시 확인하고, 목표 색상이 확인되면 멈춰 불필요한 전체 팔레트 수집을 줄입니다. 5개 언어의 안내와 설명서도 정비했습니다. 여러 영역의 정확한 일치는 보장하지 않으며 결과 적용은 게임에서 직접 결정해 주세요. 한국·일본 서버 지원은 테스트 중입니다.
