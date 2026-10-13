# 0.4.4rc2 本地测试版

在0.4.4rc1基础上优化截图寻色末尾的恢复复核：同一画面、同一目标且没有新操作时，共用刚完成的实测结果，避免多层调用重复读色。新输入、新截图、重试或最佳目标变化后重新处理；色码未读全时保留后续读取，达标仍需独立帧确认。

连续滚轮、缩放精度、定位精度及搜索策略保持0.4.4rc1的实现。仅优化重复复核，不增加停止条件或减少必要纠偏。

保存测试局的离线回放中，恢复读取由12次降到2次，实际读出颜色一致，保留原有的一次恢复移动。按原局时间记录可减少约7.36秒重复阶段；尚未新实机计时。

本地测试版，未公开发布。正式默认仍为精准寻色；测试本轮功能时选择截图寻色。多色精准命中不作成功保证。

## 繁體中文

改善截圖尋色結束前重複讀取色碼的問題。同一畫面沒有新操作時，會共用剛完成的實測結果；必要的修正與獨立確認仍保留。連續滾輪及縮放精度維持原有實作。本版僅供本機測試。

## English

Removed redundant color reads during final best-result recovery in screenshot search. Unchanged screens share the completed recovery result; new input, unreadable colors, and independent match confirmation still receive fresh checks. Wheel gestures and positioning precision are unchanged. Local preview only.

## 日本語

スクリーンショット検索の最終段階で、同じ画面の色コードを繰り返し読み取る処理を削減しました。新しい操作や読み取り失敗があれば再確認し、必要な位置補正と一致確認は維持します。ホイール操作と拡大縮小の精度は変更していません。ローカルテスト版です。

## 한국어

스크린샷 검색의 마지막 단계에서 같은 화면의 색상 코드를 반복해서 읽는 처리를 줄였습니다. 새 입력이나 읽기 실패가 있으면 다시 확인하며, 필요한 위치 보정과 일치 확인은 유지합니다. 휠 조작과 확대·축소 정밀도는 변경하지 않았습니다. 로컬 테스트 버전입니다.
