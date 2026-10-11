"""Read-only native service preflight. Does not construct a sender or enter dye."""
import argparse,datetime,json
from pathlib import Path


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int)
    parser.add_argument('--hwnd',type=int)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--korean',action='store_true',help='Locate the unique Korean client; verify its build fingerprint')
    args=parser.parse_args(argv)
    from native_live.service import preflight
    from window_target import resolve_target,list_windows
    if args.korean and args.pid is None:
        candidates=[w for w in list_windows() if w.title=='마비노기 모바일' and w.executable.casefold()=='mabinogimobile.exe']
        if len(candidates)!=1:raise ValueError('Expected one Korean game window for read-only preflight')
        target=candidates[0]
    else:target=None if args.pid is not None else resolve_target()
    pid=args.pid if args.pid is not None else target.pid
    hwnd=args.hwnd if args.hwnd is not None else target.hwnd if target is not None else None
    folder=args.output_dir or Path('outputs/native-preflight')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    result=preflight(pid,folder,hwnd=hwnd)
    if args.korean and result['stop_reason']=='preflight_complete':
        from native_live.build_adapters import KR_ADAPTER
        if result.get('build_adapter',{}).get('adapter_id')!=KR_ADAPTER.adapter_id:
            result.update(stop_reason='unavailable',unavailable_reason='game_build',error='Selected game build does not match Korean adapter')
            (folder/'native-preflight.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['stop_reason']=='preflight_complete' else 1


if __name__=='__main__':raise SystemExit(main())
