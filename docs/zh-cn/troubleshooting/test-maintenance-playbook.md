# 测试维护剧本

当古旧的测试基础设施或环境依赖导致 pytest 卡住时，最初应该检查的要点总结。

## 目的

- 区分 `failed` 和 `skipped` 
- 区分正常的环境依赖 skip 和应该修复的过时测试
- 当 broad run (`pytest tests -q --maxfail=1`) 卡住时，建立固定的最短导线

## 基本命令

正常的全体检查：

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

也检查 skip 的原因：

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

严格处理 shared test server：

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

许可证审计：

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## 解读当前的 skip

2026-04-21 时点的 broad run 中，skip 的主要原因偏向以下 5 个系统。

### 1. Shared Test Server 未启动

最常见的 skip。`tests/conftest.py` 中的 shared server 以尽力而为的方式启动，若启动失败，浏览器/服务器依赖的群组会被降级为 skip 而非 fail。

代表性的原因：

- `Shared test server unavailable on port <PORT>`

主要对象：

- `tests/api/`
- 浏览器 UX 审查类
- LAN Cowork / Fleet 浏览器/服务器依赖的测试
- 使用 `TARGET_URL` / `BASE` / `TARGET` 的 live browser test
- 使用自定义 Playwright/WebKit fixture 而非 `page` fixture 的审计类测试

在正常执行中，这是**正常的 skip**。但若出现以下情况应调查：

- 与 shared server 无关的 unit test 也因同样原因被 skip
- 以前通过的 shared server 类测试突然大量 skip 化
- 即使设置 `PYTEST_STRICT_AUTOSTART_SERVER=1` 也看不到原因

### 2. OS 专属测试

Linux 专属的 sandbox / AppArmor / process isolation 类。在 Windows 上 skip 是正确的。

代表例：

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

代表性的原因：

- `Linux only`
- `AppArmor is Linux-specific`

这是**正常的 skip**。

### 3. 任意依赖、外部组件缺失

特定包或外部节点缺失的环境中，这些测试不执行。

代表例：

- mDNS 实机 E2E：`optional zeroconf package is not installed`
- 浏览器启动：`Playwright unavailable`、`launch failed`
- ONNX / YAML / ComfyUI / 外部推论节点未连接

这是**正常的 skip**。不是修复对象，只是前置环境不完整。

### 4. 测试数据不足

需要图像、搜索结果、对话日志、多件数据等的浏览器测试，在轻量级数据库中无法进行，因此被 skip。

代表性的原因：

- `No search results available in database`
- `DB 中无图像，因此跳过`
- `需要 2 件以上的文件`
- `No prompts to test copy`

这**大致上是正常的 skip**。但若本该由 fixture 准备必要数据的测试才是过时化的嫌疑。

### 5. 速率限制、外部 API 保护

某些集成测试会尊重外部服务或速率限制而 skip。

代表性的原因：

- `因为达到速率限制而跳过`

这是**正常的 skip**。

### 6. 长时间 fuzz / burn-in

`tests/fuzz/` 下的 burn-in 用于耐久性和崩溃复原性检查，而非常规回归测试。

预设由 `pytest.ini` 中的 marker 式排除。

执行时：

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

必要时：

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

这**不应该混入常规的 broad run**。

## 应视为异常的模式

以下不应「skip 就没问题」而草草结束，应纳入测试维护对象。

### A. 以前通过的轻量级测试掉进 setup skip

例：

- 本应仅靠 app/client fixture 完整运作的 API smoke，被卷入 shared server 前提
- migration / schema / DB helper 的 unit test 因 runtime global state 初始化前提而掉落

此时应怀疑 test harness 与实装的前提不一致。

### B. broad run 通过，单独执行时才失败

典型例：

- 依赖 process-global state
- broad run 中碰巧由先行测试初始化的副作用

应将单独执行恢复到可再现的状态。

### C. Skip 原因不明确

不好的例：

- `failed`
- `not ready`
- `something wrong`

Skip 原因应简明扼要地写出「缺少什么导致跳过」。

## 修复的优先顺序

1. 修复导致 broad run 停止的 hard failure
2. 修复只在单独执行时崩溃的过时测试
3. 将浏览器/服务器依赖的 skip 改为安全的 skip，而非 fail
4. 维持任意依赖和实机依赖的 optional skip

## 此次整备固定的项目

- 浏览器/服务器依赖统一为 shared server unavailable 时 skip 而非 fail
- 许可证审计改为仅查看 `requirements*.txt` 宣告的依赖，而非整个 venv
- test DB 满足当前搜索架构的 path FTS 前提
- migration 54 / 55 已修正为对架构进化和执行时 state 未初始化不脆弱

## 迷茫时的判断基准

- 缺少前置环境→skip 即可
- 现行实装无法追踪的旧期望值→修复测试
- 依赖 broad run 副作用→修复实装或测试
- unit test 要求 process-global state→质疑设计
