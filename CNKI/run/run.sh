#!/usr/bin/env bash
# 按 config.sh 批量下载知网 PDF，并抓作者/单位；可随时中断，再次运行从断点继续。
#
# 用法：
#   cd CNKI/run && cp config.example.sh config.sh && vim config.sh
#   ./run.sh                     # 前台运行，终端显示每篇一行的简短进度
#   ./run.sh path/to/other.sh    # 使用其他配置文件
#   macOS 防休眠：caffeinate -is ./run.sh
#
# 日志：
#   $PDF_OUT/run_<FOLDER>.log           完整日志，所有轮次追加写入
#   终端                                 简短进度（不写入日志）
set -u
RUN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CNKI_DIR="$(dirname "$RUN_DIR")"
REPO_DIR="$(dirname "$CNKI_DIR")"

CONFIG="${1:-$RUN_DIR/config.sh}"
if [ ! -f "$CONFIG" ]; then
    echo "找不到配置文件 $CONFIG"
    echo "先执行： cp $RUN_DIR/config.example.sh $RUN_DIR/config.sh  然后修改"
    exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG"

PY="${PYTHON:-}"
[ -z "$PY" ] && PY="$REPO_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "找不到 Python：${PY}（先运行 setup_mac.sh，或在 config.sh 里设置 PYTHON）"
    exit 1
fi
if [ ! -f "$CNKI_DIR/cnki_unit_credentials.json" ]; then
    echo "缺少 $CNKI_DIR/cnki_unit_credentials.json"
    echo "先执行： cp $CNKI_DIR/cnki_unit_credentials.example.json $CNKI_DIR/cnki_unit_credentials.json  然后填写"
    exit 1
fi
if [ ! -d "$RECORDS_ROOT/$FOLDER" ]; then
    echo "题录目录不存在：$RECORDS_ROOT/$FOLDER"
    exit 1
fi

# select_records.py 生成的子集：最后一个 Excel 只爬前 N 篇
LAST_LIMIT=0
if [ -f "$RECORDS_ROOT/select.json" ]; then
    LAST_LIMIT=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["last_limit"])' \
                 "$RECORDS_ROOT/select.json" 2>/dev/null || echo 0)
fi

mkdir -p "$PDF_OUT" "$EXCEL_OUT"
LOG="$PDF_OUT/run_${FOLDER}.log"

# 运行环境：.venv/bin 在前（放 chromedriver），离线模式不让 selenium-manager 联网找驱动
export PATH="$(dirname "$PY"):$PATH"
export SE_OFFLINE=true PYTHONUNBUFFERED=1
export CNKI_HEADLESS="${HEADLESS:-1}"
if [ "$(uname)" = "Darwin" ]; then
    export GAP_INFER_DEVICE="${GAP_INFER_DEVICE:-cpu}" OCR_DEVICE="${OCR_DEVICE:-cpu}"
fi
export CNKI_RUN_RECORDS="$RECORDS_ROOT" CNKI_RUN_FOLDER="$FOLDER" \
       CNKI_RUN_PDF="$PDF_OUT" CNKI_RUN_COPY="$EXCEL_OUT" CNKI_RUN_LAST_LIMIT="$LAST_LIMIT"

say() { echo "$(date +%H:%M:%S) $*"; }

say "统计当前进度…"
read -r DONE0 PDF0 TOTAL < <("$PY" "$RUN_DIR/progress.py" count 2>/dev/null || echo "0 0 0")
say "已处理 ${DONE0:-0}/${TOTAL:-0}（PDF ${PDF0:-0}），开始爬取（headless=${CNKI_HEADLESS}）"
say "完整日志：$LOG"

# 完整输出只进日志；同时交给 progress.py，在终端打印简短进度
exec > >(tee -a "$LOG" | "$PY" -u "$RUN_DIR/progress.py" watch "${DONE0:-0}" "${PDF0:-0}" "${TOTAL:-0}") 2>&1

cd "$CNKI_DIR" || exit 1
COMMON=(--out "$PDF_OUT" --excel-out "$EXCEL_OUT" --folder "$FOLDER")
echo "### 开始 $(date) | 出口 IP: $(curl -s --max-time 8 https://ipinfo.io/json | grep -E '"(city|org)"' | tr -d '\n ')"
echo "### part1 $RECORDS_ROOT/$FOLDER"
"$PY" cnki_excel.py --records "$RECORDS_ROOT" "${COMMON[@]}" < /dev/null
if [ "$LAST_LIMIT" -gt 0 ] && [ -d "$RECORDS_ROOT/_last/$FOLDER" ]; then
    echo "### part2 最后一个 Excel 前 $LAST_LIMIT 篇"
    "$PY" cnki_excel.py --records "$RECORDS_ROOT/_last" "${COMMON[@]}" --limit-papers "$LAST_LIMIT" < /dev/null
fi
echo "### ALL DONE $(date)"
