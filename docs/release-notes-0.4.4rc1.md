# 0.4.4rc1 本地测试版

截图寻色新增“两区精准纯色＋一区相似色”的联合求解。两精准区域固定目标位置，第三区域按用户原容差参与排序；未同时满足三区要求的结果仍为妥协。找不到纯色样本时继续寻找接近的方案。

首批纯色点优先探索色块内部及不同位置；第三相似色候选不再被首批数量裁剪遗漏。细化从每次实际测量的位置重新规划，坏试探恢复实测最佳，恢复未完成时先处理恢复。最终达标须在未操作画板时再次读取游戏色码。

图像定位增加亚像素修正，并用独立保留像素检查改善；原始采样 RGB 和游戏色码不变。精准寻色仍为正式默认模式。

这是独立本地测试版。留存截图回放和回归测试不代表新的实机染色成功；不保证任意色板有兼顾全部目标的路线。

## English

Local preview of screenshot search for two exact colors and one similar color. Exact anchor positions stay fixed, while the third region retains the user's tolerance and priority. Candidate coverage, measured position refinement, best-result recovery, and a second game HEX check have been improved. Screenshot replay is not a new live success claim.

## 日本語

スクリーンショット検索で、2部位の完全一致色と1部位の近似色を同時に探すローカルテスト版です。完全一致の2点を固定し、3部位目も設定した許容色差と優先順位に従って評価します。位置の微調整と最良結果への復帰を改善しました。過去の画像による検証であり、実機での新たな成功を保証するものではありません。

## 한국어

스크린샷 검색으로 두 부위의 정확한 색상과 한 부위의 유사 색상을 함께 찾는 로컬 테스트 버전입니다. 정확한 색상의 두 지점을 고정하고, 세 번째 부위도 사용자가 설정한 허용 색차와 우선순위로 평가합니다. 위치 미세 조정과 최선의 결과로 돌아가는 과정을 개선했습니다. 저장된 이미지로 검증한 결과이며, 새로운 실제 염색 성공을 보장하지 않습니다.
