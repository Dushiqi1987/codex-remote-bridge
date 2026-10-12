# 按链路定位问题

按本地出口 → 本地监听 → SSH 反向监听 → 服务器代理请求 → Codex 请求的顺序排查。不要直接删认证或修改模型提供商。

| 现象 | 检查与处理 |
| --- | --- |
| `remote port forwarding failed` | 服务器 `ss -lnt` 检查 17891 是否占用；用新远端端口并同步 `configure_remote.py --port` / 隧道 `-RemotePort`。若 SSH 服务限制 `AllowTcpForwarding` 或 `PermitListen`，联系实例管理员，不擅自放宽共享服务器配置。 |
| `administratively prohibited` | SSH 服务拒绝转发；请求管理员核查允许的远端监听，不关闭 SSH 安全校验。 |
| SSH 已连接，curl 失败 | `ExitOnForwardFailure` 仅保证远端端口监听建立。在本地测试右侧端口是否真的有 HTTP 代理。检查密码登录是否完成、隧道窗口是否退出。 |
| 本地脚本报端口被占用 | `Get-NetTCPConnection -LocalPort 11450 -ErrorAction SilentlyContinue` 查看监听；不要直接结束未知进程。使用 `python scripts/local_forward.py --port 11451` 并把隧道本地目标同步改为 11451。 |
| Python 代理返回 502 | 本机 DNS、路由或目标连接失败。先验证本机直连目标能否访问；浏览器插件代理不会自动作用于 Python socket。使用代理软件方案时直接转发其 HTTP 端口。 |
| curl 连接后挂起或协议错误 | 目标可能是纯 SOCKS 端口，或代理软件未启用 HTTP。检查端口类型，不只检查“是否监听”。 |
| 服务器 curl 成功，Codex 失败 | 已运行的 Codex 没获得环境；在同一 shell 显式导出后重启，或通过 `codex_with_proxy.py` 启动。记录 Codex 版本和实际请求错误。检查 provider 自定义地址、登录域名、WebSocket 与账号状态，不能只测试 API 首页。 |
| 使用自定义 CODEX_HOME | 配置和启动器显式传同一个 `--env-file`，或在服务器 shell 使用已有 CODEX_HOME。不要在另一个目录生成后继续使用旧文件。 |
| 返回 401 / 403 | 说明收到 HTTP 响应，可能是服务、代理或网关返回；检查响应来源、账号权限、地区支持和额度，不能把这判作 Codex 成功。 |
| TLS / 证书错误 | 核查系统时间和可信根证书；有企业 TLS 拦截时按官方 `CODEX_CA_CERTIFICATE` / `SSL_CERT_FILE` 配置。不要用 `curl -k` 或关闭 TLS 校验作为解决方式。 |
| 偶尔断开 | 检查本地休眠、网络变化、代理软件和 SSH 进程。脚本默认 1 小时空闲超时；需要时调整 `--idle-timeout`，单次阻塞读写超时由 `--connect-timeout` 控制。SSH keepalive 不是自动重连。 |
| 登录需要打开浏览器 | 依据当前 `codex login --help` 选择 CLI 支持的方式，用户在自己的账号完成；网络隧道不自动转发登录回调，也不自动复制本地登录状态。 |

## 检查命令

本地 PowerShell（端口按自己的方案替换）：

```powershell
Get-NetTCPConnection -LocalPort 11450 -ErrorAction SilentlyContinue
curl.exe --noproxy "" --proxy http://127.0.0.1:11450 --connect-timeout 10 --max-time 30 -I https://api.openai.com
```

服务器 Linux：

```bash
ss -lnt | grep ':17891'
curl --noproxy '' --proxy http://127.0.0.1:17891 --connect-timeout 10 --max-time 30 -I https://api.openai.com
codex --version
codex login status
```

确认 SSH 服务的有效配置将远端端口绑定到 `127.0.0.1`。若服务器的 `GatewayPorts yes` 强制公网绑定，先停止隧道，再请管理员提供回环监听的配置；不要公开无认证代理。

## 反馈信息

收集本地出口方案、端口、SSH 错误、Codex 版本、是否通过强制代理 curl，以及一次实际 Codex 错误。输出中隐藏令牌、Authorization 头、密钥和登录验证码；代理脚本默认不记录请求 URL 和内容。
