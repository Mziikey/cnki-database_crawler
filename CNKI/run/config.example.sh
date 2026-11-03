# CNKI 批量下载 PDF 的运行配置。
# 使用前复制一份：  cp config.example.sh config.sh   然后改 config.sh（config.sh 不会提交到 git）

# 题录根目录：下面是一级子文件夹，子文件夹里放知网导出的 CNKI-*.xls
#   例：$HOME/知网题录/农业科技/CNKI-2026xxxx.xls
# 如果用 select_records.py 挑过子集，这里填它的 --dst 目录
RECORDS_ROOT="$HOME/知网题录"

# 要处理的子文件夹名（RECORDS_ROOT 下的一级目录）
FOLDER="农业科技"

# PDF 保存根目录（会按子文件夹名再建一层）
PDF_OUT="$HOME/知网PDF"

# 题录副本保存根目录（写入作者/单位对应、机构未购入等标记，也是断点续爬的依据）
EXCEL_OUT="$HOME/知网题录副本"

# 1=无头（不弹浏览器窗口），0=有头（第一次跑建议 0，便于观察登录/验证码）
HEADLESS=1

# Python 解释器；留空则用仓库根目录的 .venv（setup_mac.sh 创建）
PYTHON=""
