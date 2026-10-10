"""Read-only native service preflight. Does not construct a sender or enter dye."""
import argparse,datetime,json
from pathlib import Path


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int)
    parser.add_argument('--hwnd',type=int)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args(argv)
    from native_live.service import preflight
    from window_target import resolve_target
    target=None if args.pid is not None else resolve_target()
    pid=args.pid if args.pid is not None else target.pid
    hwnd=args.hwnd if args.hwnd is not None else target.hwnd if target is not None else None
    folder=args.output_dir or Path('outputs/native-preflight')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    result=preflight(pid,folder,hwnd=hwnd)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['stop_reason']=='preflight_complete' else 1


if __name__=='__main__':raise SystemExit(main())
