"""进度统计与终端简报（由 run.sh 调用，一般不用手动运行）。

  progress.py count   打印「已处理篇数 PDF数 总篇数」
  progress.py watch DONE PDF TOTAL   从 stdin 读爬虫日志，每篇向终端输出一行进度

配置来自 run.sh 导出的环境变量：
  CNKI_RUN_RECORDS  CNKI_RUN_FOLDER  CNKI_RUN_PDF  CNKI_RUN_COPY  CNKI_RUN_LAST_LIMIT
watch 写到 /dev/tty（不进日志文件）；没有终端时只读不写。PROGRESS_STDOUT=1 时写 stdout。
"""
import os
import re
import sys
import time
from pathlib import Path

DONE_MARKS = ('机构未购入', '无PDF', '仅题录', '404', '无作者单位')
PAT_EXCEL = re.compile(r'======== Excel (\d+/\d+)')
PAT_PAPER = re.compile(r'^\s*\[(\d+/\d+) · ')
PAT_PENDING = re.compile(r'URL \d+ 条，已完成跳过 \d+，待处理 (\d+)')


def _env_path(name):
    return Path(os.environ[name]).expanduser()


def count_done():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import cnki_excel as c

    records = _env_path('CNKI_RUN_RECORDS')
    folder = os.environ['CNKI_RUN_FOLDER']
    copy_dir = _env_path('CNKI_RUN_COPY') / folder
    pdf_dir = _env_path('CNKI_RUN_PDF') / folder
    last_limit = int(os.environ.get('CNKI_RUN_LAST_LIMIT') or 0)

    # 与 cnki_excel.py 用同一套文件枚举规则（跳过 captcha_debug、~$ 临时文件等）
    groups = [(c.iter_excel_files(records / folder), 0)]
    last_dir = records / '_last' / folder
    if last_limit and last_dir.is_dir():
        groups.append((c.iter_excel_files(last_dir), last_limit))
    total = done = pdf = 0
    for files, limit in groups:
        for f in files:
            papers = c.load_papers_from_excel(f)
            if limit:
                papers = papers[:limit]
            total += len(papers)
            cp = copy_dir / (f.stem + '.xlsx')
            df = c.read_excel_table(cp) if cp.exists() else None
            for p in papers:
                if (pdf_dir / p['filename']).exists():
                    pdf += 1
                    done += 1
                elif df is not None:
                    s = ' '.join(str(df.at[p['df_index'], k])
                                 for k in c.AUTHOR_ORG_COLS if k in df.columns)
                    if any(m in s for m in DONE_MARKS):
                        done += 1
    return done, pdf, total


class Watcher:
    def __init__(self, done, pdf, total):
        self.done, self.pdf, self.total = done, pdf, total
        self.unav = self.fail = 0
        self.excel = self.pos = '?'
        if os.environ.get('PROGRESS_STDOUT'):
            self.out = sys.stdout
        else:
            try:
                self.out = open('/dev/tty', 'w', encoding='utf-8')
            except OSError:
                self.out = None

    def say(self, msg):
        if not self.out:
            return
        try:
            self.out.write(f'{time.strftime("%H:%M:%S")} {msg}\n')
            self.out.flush()
        except Exception:
            self.out = None  # 终端关了也要继续读完 stdin，否则 tee 会收到 SIGPIPE

    def tally(self, tag):
        self.say(f'Excel {self.excel} [{self.pos}] {tag} | 总 {self.done}/{self.total}'
                 f'（PDF {self.pdf}，本轮未购入 {self.unav}，失败 {self.fail}）')

    def handle(self, line):
        m = PAT_EXCEL.search(line)
        if m:
            self.excel = m.group(1)
            return
        m = PAT_PENDING.search(line)
        if m:
            self.say(f'── Excel {self.excel} 开始，本表待处理 {m.group(1)} 篇')
            return
        m = PAT_PAPER.match(line)
        if m:
            self.pos = m.group(1)
            return
        if '✓ PDF 成功' in line:
            self.done += 1
            self.pdf += 1
            self.tally('✓PDF')
        elif '⊘ 机构未购入' in line:
            self.done += 1
            self.unav += 1
            self.tally('未购入')
        elif '⊘' in line and '并继续' in line:
            # 只算单篇标记；「⊘ [n/N] 已完成，跳过」是整表跳过，不计数
            self.done += 1
            self.tally('无PDF')
        elif '✗ PDF 失败' in line or '本篇失败' in line:
            self.fail += 1
            self.tally('✗失败')
        elif '腾讯限流：' in line:
            self.say('⏸ 被限流，关闭浏览器等待 5 分钟后继续')
        elif '机构 IP 登录超时' in line:
            self.say('⚠ 机构 IP 登录失败：确认在机构网络内且没开代理')
        elif 'WebVPN 登录超时' in line:
            self.say('⚠ WebVPN 登录失败：检查账号密码与网络')
        elif '连续 3 次无法启动' in line or 'ERR_INTERNET_DISCONNECTED' in line:
            self.say('⚠ 浏览器启动失败/网络断开')
        elif 'Traceback' in line:
            self.say('⚠ 程序报错，详见日志')
        elif line.startswith('### ALL DONE'):
            self.say(f'■ 全部完成：总 {self.done}/{self.total}，PDF {self.pdf}')


def watch(done, pdf, total):
    w = Watcher(done, pdf, total)
    for line in sys.stdin:
        try:
            w.handle(line.rstrip('\n'))
        except Exception:
            pass  # 任何解析问题都不能中断管道


if __name__ == '__main__':
    if sys.argv[1:2] == ['count']:
        print(*count_done())
    elif sys.argv[1:2] == ['watch']:
        watch(*(int(x) for x in sys.argv[2:5]))
