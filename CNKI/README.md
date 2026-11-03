# CNKI（中国知网）

本目录为知网题录导出、全文 PDF、验证码处理与结果统计相关脚本。

## 文件说明

### 核心流程

| 文件 | 作用 |
|------|------|
| `cnkiforexcel.py` | 主流程：高级检索 → 导出题录 Excel（期刊 / 专利、文献分类、可选主题、日期粒度、单位登录与验证码） |
| `cnki.py` | 较早的 PDF 下载工具（按时间段 / 学科目录下载，依赖 `cnkiforexcel` 登录与验证码能力） |
| `cnki_excel.py` | 根据已导出的 `CNKI-*.xls/xlsx` 中的 URL 批量下载 PDF，并抓取作者单位等 |
| `cnki_author.py` | 从详情页补充作者与单位信息到 Excel |

### 验证码与登录

| 文件 | 作用 |
|------|------|
| `cnki_captcha.py` | 验证码公共模块（腾讯验证码、滑块 blockPuzzle、文字点选等） |
| `cnki_unit_credentials.example.json` | 单位登录凭证模板（复制为下方正式文件后填写） |
| `cnki_unit_credentials.json` | 单位登录凭证（本地使用，勿外传） |
| `test_block_puzzle_captcha.py` | 滑块验证码联调 |
| `test_text_click.py` | 文字点选验证码联调 |
| `test_anticap.py` | AntiCAP 相关试验 |
| `Text_select_captcha/` | 文字点选验证码服务与模型相关代码包 |

### 统计与质检

| 文件 | 作用 |
|------|------|
| `cnki_summary.py` | 统计题录覆盖、缺失时段、重复记录，生成汇总表 |
| `cnki_fill_failures.py` | 根据汇总结果整理/补写失败时段日志 |
| `cnki_dedup_files.py` | 按汇总中的重复信息删除冗余题录文件 |

## 建议运行顺序

1. 配置 `cnki_unit_credentials.json`（可参考 example）。
2. 运行 `cnkiforexcel.py` 导出题录。
3. 需要全文时运行 `cnki_excel.py`（或历史流程 `cnki.py`）。
4. 用 `cnki_summary.py` 做覆盖与重复检查，必要时去重或补失败时段。
5. 需要作者-单位对应时运行 `cnki_author.py`：无参数运行会进入交互模式，按提示输入源目录、输出目录、并发数、文件/论文上限等；也可用 `--folder`、`--out` 等参数非交互运行。

## 期刊 / 专利题录导出

在 `cnkiforexcel.py` 中通过任务字段或交互配置：

| 字段 | 说明 |
|------|------|
| `doc_type` | `journal`（学术期刊）、`patent`（专利库 `classid=VUDIXAIY`）或 `none`（不选，跳过结果页资源类型筛选） |
| `lang` | `zh`=中文、`en`=英文、`none`=不选（跳过检索页/结果页中/外文筛选） |
| `category` | 期刊=学科导航；专利=国际专利分类 IPC（如 `['G','G06']`） |
| `theme` | 可选主题；专利写入第2行「主题」(SU)，不填「公开号」 |
| `patent_date` | 专利：`AD`=申请日 / `OD`=公开日（默认申请日） |
| `bgdate` / `initdate` / `granularity` | 日期范围与切分粒度 |

专利检索流程与期刊不同：重置条件 → 展开 IPC 侧栏 → 勾选分类号 → 主题行 → 申请日或公开日（互斥）→ 检索；结果页不再点 JOURNAL。

```bash
python cnkiforexcel.py --doc-type patent
python cnkiforexcel.py --doc-type journal
python cnkiforexcel.py --doc-type none   # 不选导出类型，跳过资源类型筛选
```

选择「不选」时：`doc_type=none` 不点 JOURNAL/PATENT；`lang=none` 不勾选中/外文，也不点结果页语言 tab。

专利结果保存到 `DOWNLOAD_ROOT/专利/...`；带主题时目录名会追加主题后缀。

## 注意

- 请在本目录（`code/CNKI`）下执行脚本，以保证同目录模块互相导入正常。
- 下载根目录等路径多在脚本内配置或通过命令行参数指定，与代码目录相互独立。

## 无头模式（headless）

参考 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的做法，三个浏览器脚本
（`cnkiforexcel.py`、`cnki_excel.py`、`cnki.py`）现在通过 `chrome_launcher.py` 启动浏览器：

- 不走 chromedriver 自动化注入，直接以 `--remote-debugging-port` 启动本机真实 Chrome，
  Selenium 通过 `debugger_address` 连接；找不到本机 Chrome 时自动回退 chromedriver。
- 每个新页面加载前注入 `libs/stealth.min.js`（puppeteer-extra-stealth 产物），
  抹掉 `navigator.webdriver`、WebGL 指纹等自动化特征。
- 无头模式下用 CDP 覆盖 UA，去掉 `HeadlessChrome` 标记。

环境变量：

| 变量 | 说明 |
|---|---|
| `CNKI_HEADLESS=1` | 无头模式（默认有头；建议先有头跑通一次验证码再切无头） |
| `CNKI_NO_STEALTH=1` | 不注入 stealth.min.js（调试用） |
| `CNKI_CHROME_BINARY` | 覆盖自动探测的 Chrome 路径 |
| `CNKI_USER_AGENT` | 覆盖无头模式下的伪装 UA |

注意：点选文字验证码的合成点击（`isTrusted=false`）在无头下被风控拒收的风险更高，
若验证码连败，把 `CNKI_HEADLESS` 关掉切回有头模式排查。

## 网络环境要求（WebVPN / IP 直连）

`cnki_unit_credentials.json` 的 `method` 字段决定登录方式：
`vpn`（WebVPN + CAS）、`ip`（校园网内知网自动认机构 IP）、`school_visit`（校外访问）。

**WebVPN 模式要求出口 IP 稳定。** 学校 WebVPN 把会话票据绑定到登录时的客户端
IP，出口 IP 一变就强制注销（URL 带 `logoutByIpChange=true`），表现为「登录成功
→几秒后失效→反复重登」。公司内网（多出口 NAT 轮换）下该模式不可用；请用家庭
宽带、手机热点等单出口网络，或在校园网内直接用 `ip` 模式。

## 本轮修复（2026-11）

- **误标修复**（`cnki_excel.py`）：WebVPN 重认证把页面带离详情页后，原逻辑会把
  该文献误标为「无PDF」并给整个 Excel 写 `.done`。现在要求必须确实在详情页上、
  且从未见过 PDF 按钮才允许写跳过标记；其余情况一律重试，重试耗尽只记 fail
  （下次运行继续处理）。`机构未购入`/`仅题录`/`无PDF` 三种真实错误的判定与标记
  逻辑保持不变。
- **门户兜底**（`cnkiforexcel.py`）：CAS 提交后若门户资源块未加载、或点击知网
  资源块后页面未跳转（无头下 JS 点击偶发不生效），每 15 秒直接导航 WebVPN 包装
  的知网地址，不再干等 180 秒超时。
- **登录超时诊断**：WebVPN 登录超时会打印最终停留的页面 URL。
- **Selenium 命令超时**（`cnki_excel.py`）：`command_executor.set_timeout(120)`，
  防止下载流僵死时主线程永久挂起。

待验证（需稳定网络环境）：无头模式下点击 PDF → 文件落盘的端到端链路；
`cnki_excel.py` 中 `[debug]` 标签页转储保留，若下载不落盘可直接从日志定位。
