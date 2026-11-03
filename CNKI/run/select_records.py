"""按发表日期 / 篇数从题录文件夹里挑一个子集，供 run.sh 爬取。

不复制、不修改原始题录：在 --dst 下建符号链接。例：

  # 2023 年里按日期顺序的前 10000 篇
  python select_records.py --src ~/知网题录/农业科技 --dst ~/知网题录_2023前1万 \
      --from-date 2023-01-01 --to-date 2023-12-31 --max-papers 10000

结果：
  <dst>/<子文件夹名>/CNKI-*.xls          完整爬取的 Excel
  <dst>/_last/<子文件夹名>/CNKI-*.xls    最后一个 Excel（只爬前 N 篇，凑满 --max-papers）
  <dst>/select.json                      选择结果，run.sh 会读取其中的 last_limit

然后在 config.sh 里设  RECORDS_ROOT=<dst>  FOLDER=<子文件夹名>。
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cnki_excel as c  # noqa: E402


def first_date(path: Path) -> str:
    """Excel 中最早的发表日期，统一成 YYYY-MM-DD（知网偶有 2023-1-3 这种不补零的写法）。"""
    import pandas as pd
    df = c.read_excel_table(path)
    for col in ('PubTime-发表时间', 'Year-年', '年'):
        if col in df.columns:
            raw = df[col].dropna().astype(str).str.strip().str.split().str[0]
            dates = pd.to_datetime(raw, errors='coerce').dropna()
            if len(dates):
                return dates.min().strftime('%Y-%m-%d')
    return ''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', type=Path, required=True, help='放 CNKI-*.xls 的题录子文件夹')
    ap.add_argument('--dst', type=Path, required=True, help='输出的子集根目录（新建）')
    ap.add_argument('--from-date', default='', help='起始日期 YYYY-MM-DD（含）')
    ap.add_argument('--to-date', default='', help='结束日期 YYYY-MM-DD（含）')
    ap.add_argument('--max-papers', type=int, default=0, help='最多多少篇（0=不限）')
    args = ap.parse_args()

    src = args.src.expanduser().resolve()
    files = sorted(p for p in src.glob('CNKI-*.xls*') if not p.name.endswith(('.done', '.lock')))
    if not files:
        print(f'{src} 下没有 CNKI-*.xls')
        return 1

    print(f'读取 {len(files)} 个 Excel 的日期…')
    rows = []
    for f in files:
        d = first_date(f)
        if args.from_date and d < args.from_date:
            continue
        if not d or (args.to_date and d > args.to_date):
            continue
        rows.append((d, f, len(c.load_papers_from_excel(f))))
    rows.sort()
    if not rows:
        print('没有符合日期范围的 Excel')
        return 1

    picked, total, last_limit = [], 0, 0
    for d, f, n in rows:
        if args.max_papers and total >= args.max_papers:
            break
        need = args.max_papers - total if args.max_papers else n
        picked.append((d, f, n))
        if args.max_papers and n > need:
            last_limit = need
            total += need
        else:
            total += n

    folder = src.name
    dst = args.dst.expanduser()
    if dst.exists() and any(dst.iterdir()):
        print(f'{dst} 已存在且非空，请换一个目录或先清空')
        return 1
    full_dir = dst / folder
    full_dir.mkdir(parents=True, exist_ok=True)
    for i, (_, f, _) in enumerate(picked):
        if last_limit and i == len(picked) - 1:
            last_dir = dst / '_last' / folder
            last_dir.mkdir(parents=True, exist_ok=True)
            os.symlink(f, last_dir / f.name)
        else:
            os.symlink(f, full_dir / f.name)

    info = {
        'src': str(src), 'folder': folder, 'total': total,
        'files': len(picked), 'from': picked[0][0], 'to': picked[-1][0],
        'last_file': picked[-1][1].name if last_limit else '',
        'last_limit': last_limit,
    }
    (dst / 'select.json').write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                     encoding='utf-8')
    print(f'已选 {len(picked)} 个 Excel，共 {total} 篇，日期 {info["from"]} → {info["to"]}')
    if last_limit:
        print(f'最后一个 Excel {info["last_file"]} 只爬前 {last_limit} 篇')
    print(f'在 config.sh 里设置：RECORDS_ROOT="{dst}"  FOLDER="{folder}"')
    return 0


if __name__ == '__main__':
    sys.exit(main())
