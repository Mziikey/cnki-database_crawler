"""统一的 Chrome 启动模块。

参考 MediaCrawler 的做法：不走 chromedriver 自动化注入，直接用
--remote-debugging-port 启动本机真实 Chrome，再用 Selenium 的
debugger_address 连接。配合 stealth.min.js 注入，降低无头模式下
被风控识别的概率。

环境变量:
  CNKI_HEADLESS=1        无头模式（默认有头）
  CNKI_NO_STEALTH=1      不注入 stealth.min.js（调试用）
  CNKI_CHROME_BINARY     覆盖自动探测的 Chrome 路径
  CNKI_USER_AGENT        覆盖无头模式的 UA（默认按本机系统与 Chrome 版本生成）
  CNKI_USER_DATA_DIR     持久化登录态目录（默认复用上一次的 profile，
                         避免每次都重新 VPN/CAS 登录触发验证码）
"""

import os
import platform
import socket
import subprocess
import sys
import time

_STEALTH_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'libs', 'stealth.min.js')

WINDOW_SIZE = '1920,1080'

# 不带这个参数时，JS 触发的 click()/window.open 打开新窗口会被弹窗拦截，
# 知网 PDF 下载窗口就打不开（chromedriver 启动 Chrome 时会自动加上它）
_POPUP_ARG = '--disable-popup-blocking'

# 由本模块管理、不允许调用方 options 重复传入的启动参数前缀
_MANAGED_ARG_PREFIXES = (
    '--remote-debugging-port', '--headless', '--user-agent', '--window-size',
)


def headless_enabled() -> bool:
    return os.environ.get('CNKI_HEADLESS', '').strip().lower() in ('1', 'true', 'yes')


def _chrome_major_version(binary: str) -> str:
    """读取本机 Chrome 主版本号（如 156），失败返回空串。"""
    try:
        out = subprocess.run(
            [binary, '--version'], capture_output=True, text=True,
            timeout=15, check=False).stdout
    except Exception:
        return ''
    for token in out.split():
        head = token.split('.')[0]
        if head.isdigit() and '.' in token:
            return head
    return ''


def _platform_ua_token() -> str:
    system = platform.system()
    if system == 'Darwin':
        return 'Macintosh; Intel Mac OS X 10_15_7'
    if system == 'Windows':
        return 'Windows NT 10.0; Win64; x64'
    return 'X11; Linux x86_64'


def headless_user_agent(binary: str) -> str:
    """无头模式用的 UA：与本机系统、真实 Chrome 版本一致，只去掉 HeadlessChrome。

    以启动参数 --user-agent 传入，对所有标签页（含知网下载/验证码新窗口）生效。
    可用 CNKI_USER_AGENT 环境变量覆盖。
    """
    override = os.environ.get('CNKI_USER_AGENT', '').strip()
    if override:
        return override
    major = _chrome_major_version(binary) or '131'
    return (f'Mozilla/5.0 ({_platform_ua_token()}) AppleWebKit/537.36 '
            f'(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36')


def apply_fallback_options(options) -> None:
    """chromedriver 回退模式下补上无头、UA 与弹窗参数，避免回退后又弹出窗口。"""
    if headless_enabled():
        options.add_argument('--headless=new')
        options.add_argument('--window-size=' + WINDOW_SIZE)
        binary = _detect_chrome_binary()
        if binary and os.path.isfile(binary):
            options.add_argument('--user-agent=' + headless_user_agent(binary))
    if _POPUP_ARG not in options.arguments:
        options.add_argument(_POPUP_ARG)


def _detect_chrome_binary() -> str:
    override = os.environ.get('CNKI_CHROME_BINARY', '').strip()
    if override:
        return override
    system = platform.system()
    if system == 'Darwin':
        candidates = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        ]
    elif system == 'Windows':
        candidates = [
            os.path.expandvars(r'%PROGRAMFILES%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe'),
        ]
    else:
        candidates = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium-browser',
            '/usr/bin/chromium',
            '/usr/bin/microsoft-edge',
        ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    # 兜底：交给 Selenium/Chrome for Testing 管理
    return ''


def _find_available_port(start_port: int) -> int:
    port = start_port
    for _ in range(200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f'找不到可用调试端口（{start_port} 起 200 个都被占用）')


def _wait_debug_port_ready(debug_port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex(('localhost', debug_port)) == 0:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _persistent_profile_dir(default_root: str) -> str:
    """登录态持久化：默认固定目录，多次运行共用同一 profile。

    VPN/CAS 登录 cookie 留在这个 profile 里，之后启动不再触发登录验证码。
    临时 profile（脚本自己建的 tempfile.mkdtemp）不受影响。
    """
    override = os.environ.get('CNKI_USER_DATA_DIR', '').strip()
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    path = os.path.join(default_root, 'persistent_profile')
    os.makedirs(path, exist_ok=True)
    return path


def launch_chrome_and_connect(
    options,
    profile_root=None,
    port_base=9222,
    persistent=False,
):
    """启动真实 Chrome 并让 Selenium 通过 CDP 连接，返回 (driver, chrome_proc)。

    options 是调用方已建好的 selenium Options；本函数会补上
    user-data-dir / debugger_address / 反检测参数。
    调用方结束时应调用 close_launched_chrome(driver, chrome_proc)。
    """
    from selenium import webdriver

    binary = _detect_chrome_binary()
    if not binary:
        # 找不到本机 Chrome，退回老路（chromedriver 自动管理）
        print('未找到本机 Chrome，回退 chromedriver 模式')
        driver = webdriver.Chrome(options=options)
        return driver, None

    debug_port = _find_available_port(port_base)
    caller_args = list(options.arguments)
    caller_profile = next(
        (a.split('=', 1)[1] for a in caller_args if a.startswith('--user-data-dir=')),
        None)
    if caller_profile:
        user_data_dir = caller_profile  # 调用方的临时 profile 优先
    elif persistent:
        user_data_dir = _persistent_profile_dir(profile_root or os.getcwd())
    else:
        user_data_dir = None

    args = [
        binary,
        f'--remote-debugging-port={debug_port}',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-features=TranslateUI,ScreenAI,PdfOcr,LiveCaption,ReadAnything',
        '--disable-sync',
        '--disable-dev-shm-usage',
        '--no-sandbox',
        '--disable-blink-features=AutomationControlled',
        _POPUP_ARG,
        '--window-size=' + WINDOW_SIZE,
    ]
    if headless_enabled():
        args += ['--headless=new', '--disable-gpu',
                 '--user-agent=' + headless_user_agent(binary)]
    if user_data_dir:
        args.append(f'--user-data-dir={user_data_dir}')
    # 透传调用方的其余启动参数（缓存目录、--disable-features 等）
    for arg in caller_args:
        if arg.startswith('--user-data-dir=') or arg in args:
            continue
        if arg.startswith(_MANAGED_ARG_PREFIXES):
            continue
        args.append(arg)
    # 同名开关 Chrome 只认最后一个，多个 --disable-features 合并成一个
    features = []
    for arg in [a for a in args if a.startswith('--disable-features=')]:
        args.remove(arg)
        for f in arg.split('=', 1)[1].split(','):
            if f and f not in features:
                features.append(f)
    if features:
        args.append('--disable-features=' + ','.join(features))
    print(f'启动 Chrome: {binary} | debug-port={debug_port} | '
          f'headless={headless_enabled()} | user-data-dir={user_data_dir or "默认"}')
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
        preexec_fn=None if sys.platform == 'win32' else os.setsid,
    )
    if not _wait_debug_port_ready(debug_port):
        proc.terminate()
        raise RuntimeError(f'Chrome 调试端口 {debug_port} 未就绪')

    connect_options = _copy_options_for_attach(options, debug_port)
    driver = webdriver.Chrome(options=connect_options)
    inject_stealth(driver)
    # 无头 UA 已通过启动参数 --user-agent 设置，对所有标签页生效；
    # 不再用 CDP Network.setUserAgentOverride（只作用于当前标签页）
    return driver, proc


def _copy_options_for_attach(options, debug_port: int):
    """构造 attach 用的 Options：保留 prefs/UA，去掉启动类参数。"""
    from selenium.webdriver.chrome.options import Options as ChromeOptions

    new_opts = ChromeOptions()
    try:
        prefs = options.experimental_options.get('prefs', {})
        if prefs:
            new_opts.add_experimental_option('prefs', dict(prefs))
        for key, value in options.experimental_options.items():
            if key != 'prefs':
                new_opts.add_experimental_option(key, value)
    except Exception:
        pass
    new_opts.add_argument('--window-size=' + WINDOW_SIZE)
    new_opts.debugger_address = f'127.0.0.1:{debug_port}'
    return new_opts


def inject_stealth(driver):
    """每个新页面加载前注入 stealth.min.js（替代手写的 webdriver 隐藏）。"""
    if os.environ.get('CNKI_NO_STEALTH', '').strip().lower() in ('1', 'true', 'yes'):
        return
    if not os.path.isfile(_STEALTH_JS):
        print(f'stealth 脚本不存在: {_STEALTH_JS}')
        return
    try:
        with open(_STEALTH_JS, 'r', encoding='utf-8') as f:
            source = f.read()
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                               {'source': source})
        print('已注入 stealth.min.js')
    except Exception as e:
        print('stealth 注入失败（不影响运行）:', e)


def close_launched_chrome(driver, chrome_proc):
    """先 quit driver，再确保 Chrome 进程退出。"""
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
    if chrome_proc is not None:
        try:
            chrome_proc.terminate()
            chrome_proc.wait(timeout=5)
        except Exception:
            try:
                if sys.platform == 'win32':
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', str(chrome_proc.pid)],
                        capture_output=True, timeout=10, check=False)
                else:
                    os.killpg(os.getpgid(chrome_proc.pid), 9)
            except Exception:
                pass


def set_download_dir(driver, download_dir):
    """CDP 方式设置下载目录（headless=new 下 prefs 不生效，必须用这个）。"""
    abs_dir = os.path.abspath(download_dir)
    os.makedirs(abs_dir, exist_ok=True)
    payload = {'behavior': 'allow', 'downloadPath': abs_dir}
    for cmd in ('Page.setDownloadBehavior', 'Browser.setDownloadBehavior'):
        try:
            driver.execute_cdp_cmd(cmd, payload)
            print(f'已设置下载目录: {abs_dir}')
            return True
        except Exception:
            continue
    print('设置下载目录失败')
    return False


def set_window_size(driver):
    """无头模式下替代 maximize_window()。"""
    try:
        driver.set_window_size(*[int(x) for x in WINDOW_SIZE.split(',')])
    except Exception:
        pass
