"""Preview an offline review.json in the real overlay; selection sends no input."""
import argparse
import json
import ctypes
from pathlib import Path
import customtkinter as ct
from search_overlay import SearchOverlay


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review')
    args=parser.parse_args()
    data=json.loads(Path(args.review).read_text(encoding='utf-8'))
    root=ct.CTk();root.withdraw()
    def selected(batch,candidate):
        overlay.render('已选择方案 · 离线预览',f'方案 {candidate+1} 已选中。\n本窗口仅供审阅，不会操作游戏。')
    overlay=SearchOverlay(root,root.destroy,selected)
    overlay.title('Color Studio atlas preview')
    # Offline preview has no game capture loop; include it in screenshots so the
    # rendered candidate list can be inspected. Live overlay keeps its exclusion.
    ctypes.windll.user32.SetWindowDisplayAffinity(overlay.native,0)
    overlay.show_candidates(dict(batch_id='offline-preview',candidates=data['candidates']))
    overlay.stop_button.configure(text='关闭预览')
    overlay.render('本局计算结果 · 离线预览','示例目标为进入前的原色，列表显示预测色差。\n点击选择仅作预览，不会移动鼠标或确认染色。')
    overlay.deiconify();root.mainloop()


if __name__=='__main__':main()
