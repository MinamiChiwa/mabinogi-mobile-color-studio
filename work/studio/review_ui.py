"""Manual UI inspection host: isolated preferences, no game input or hotkeys."""
import argparse
import tempfile
from pathlib import Path
from unittest.mock import patch
import app
import i18n
from search_overlay import SearchOverlay
from ui_dialogs import support_dialog,tutorial_dialog


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--language',default='English')
    parser.add_argument('--surface',default='main',choices=('main','support','tutorial','overlay','history','picker','palette'))
    parser.add_argument('--size',default='1120x900');parser.add_argument('--seconds',type=int,default=180)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as folder,patch.object(app,'DATA',Path(folder)),patch.object(app.App,'hotkey_loop',lambda _:None):
        i18n.set_language(args.language)
        root=app.App();root.go=lambda *a,**k:None
        root.title('UI review · '+args.surface);root.after(200,lambda:root.geometry(args.size+'+30+40'))
        def ready():
            if args.surface=='support':support_dialog(root)
            elif args.surface=='tutorial':tutorial_dialog(root)
            elif args.surface=='history':root.show_history()
            elif args.surface=='picker':root.pick_window()
            elif args.surface=='palette':root.cards[0].open_palette()
            elif args.surface=='overlay':
                overlay=SearchOverlay(root,lambda:overlay.dismiss(),lambda *a:None)
                root.overlay=overlay
                rules=[dict(enabled=True,colors=['#808080'],exact=i<2,tolerance=12) for i in range(3)]
                overlay.begin(rules)
                rows=[dict(id=i,colors=['#808080','#808080','#707070'],deltas=[0,0,8+i],
                           maximum=8+i,average=(8+i)/3,accepted=i<3,exact_total=2,exact_matches=2) for i in range(8)]
                overlay.handle('atlas_candidates',dict(batch_id='preview',candidates=rows,default_id=0))
                overlay.handle('atlas_default_verified',dict(candidate_id=0,accepted=True,actual_colors=rows[0]['colors'],maximum=8))
        root.after(450,ready);root.after(args.seconds*1000,root.close);root.mainloop()


if __name__=='__main__':main()
