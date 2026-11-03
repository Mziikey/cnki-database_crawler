#!/usr/bin/env bash
# macOS / Linux 一键准备运行环境（国内网络友好）：
#   1. 在仓库根目录建 .venv（Python 3.10–3.12）
#   2. 用清华镜像安装 requirements.txt + captcha-recognizer（腾讯滑块缺口识别必需）
#   3. 从 npmmirror 下载与本机 Chrome 版本匹配的 chromedriver 放进 .venv/bin
#      （selenium 默认去 googlechromelabs.github.io 下载，国内常年连不上会卡死）
#
# 用法： bash CNKI/run/setup_mac.sh
# 可选环境变量： PIP_INDEX（默认清华镜像）  PYTHON_VERSION（默认 3.10）
set -euo pipefail
RUN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$(dirname "$RUN_DIR")")"
VENV="$REPO_DIR/.venv"
INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PYVER="${PYTHON_VERSION:-3.10}"

echo "== 1/3 创建虚拟环境 $VENV"
if command -v uv >/dev/null 2>&1; then
    [ -x "$VENV/bin/python" ] || uv venv --python "$PYVER" "$VENV"
    PIP=(uv pip install --python "$VENV/bin/python" --index-url "$INDEX")
else
    if [ ! -x "$VENV/bin/python" ]; then
        PY=$(command -v "python$PYVER" || command -v python3)
        "$PY" -c 'import sys; v=sys.version_info; assert (3,10)<=v[:2]<=(3,12), v' \
            || { echo "需要 Python 3.10–3.12（可先 brew install uv 或 python@3.10）"; exit 1; }
        "$PY" -m venv "$VENV"
    fi
    PIP=("$VENV/bin/python" -m pip install -i "$INDEX")
fi

echo "== 2/3 安装依赖（含 captcha-recognizer，会带上 torch，体积较大）"
export UV_HTTP_TIMEOUT=300
"${PIP[@]}" -r "$REPO_DIR/requirements.txt"
"${PIP[@]}" captcha-recognizer==0.6.0

echo "== 3/3 下载 chromedriver"
case "$(uname)" in
    Darwin) CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            [ "$(uname -m)" = arm64 ] && PLAT=mac-arm64 || PLAT=mac-x64 ;;
    *)      CHROME="$(command -v google-chrome || command -v google-chrome-stable || true)"
            PLAT=linux64 ;;
esac
if [ -z "$CHROME" ] || [ ! -x "$CHROME" ]; then
    echo "没找到 Chrome，请先安装 Google Chrome 后重跑本脚本"; exit 1
fi
VER=$("$CHROME" --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')
MAJOR=${VER%%.*}
BASE=https://registry.npmmirror.com/-/binary/chrome-for-testing
# 优先完全相同的版本，没有就取同一主版本里最新的
LIST=$(curl -sSL --max-time 30 "$BASE/")
PICK=$(printf '%s' "$LIST" | grep -oE "\"$VER/\"" | head -1 | tr -d '"/' || true)
if [ -z "$PICK" ]; then
    PICK=$(printf '%s' "$LIST" | grep -oE "\"$MAJOR\.[0-9.]+/\"" | tr -d '"/' | sort -t. -k3,3n -k4,4n | tail -1 || true)
fi
[ -n "$PICK" ] || { echo "npmmirror 上找不到 Chrome $MAJOR 对应的 chromedriver"; exit 1; }
TMP=$(mktemp -d)
curl -sSL --max-time 300 -o "$TMP/cd.zip" "$BASE/$PICK/$PLAT/chromedriver-$PLAT.zip"
unzip -q "$TMP/cd.zip" -d "$TMP"
cp "$TMP/chromedriver-$PLAT/chromedriver" "$VENV/bin/chromedriver"
chmod +x "$VENV/bin/chromedriver"
[ "$(uname)" = Darwin ] && xattr -c "$VENV/bin/chromedriver" 2>/dev/null || true
rm -rf "$TMP"
echo "Chrome $VER / $("$VENV/bin/chromedriver" --version | cut -d' ' -f1-2)"

echo "== 完成。下一步："
echo "  cp $REPO_DIR/CNKI/cnki_unit_credentials.example.json $REPO_DIR/CNKI/cnki_unit_credentials.json  # 填账号"
echo "  cp $RUN_DIR/config.example.sh $RUN_DIR/config.sh  # 填题录目录"
echo "  $RUN_DIR/run.sh"
