---
name: codex-remote-bridge
description: 为 AutoDL 等 GPU 服务器上的 Codex CLI 配置 SSH 反向端口转发，共享 Windows 本地 HTTP 代理或本地可直连网络，并检查代理环境、连通性和回滚。适用于服务器不能访问 Codex 服务、本地电脑可以访问的场景。
---

# 本地 Codex 连接服务器 Codex CLI

让服务器 Codex CLI 的 HTTP/HTTPS 请求经由 SSH 隧道从本地电脑发出。这里连接的是网络出口；本地 Codex 与服务器 Codex 不共享会话或登录状态。

## 获取参数并选方案

从用户提供的 SSH 命令提取主机、SSH 端口、用户名和可选密钥路径。未提供的连接参数才询问，不把文档示例当成真实服务器。默认远端代理端口 `17891`，本地监听端口 `11450`，冲突时同步调整配置和隧道。

- **本地有代理软件**：确认它的 HTTP 或 mixed 端口以及本地访问测试结果。直接把远端端口转发到该本地端口；不额外运行 Python 转发器。纯 SOCKS 端口不能使用 `http://` 地址冒充 HTTP 代理。
- **本地网络能直接访问**：运行 `scripts/local_forward.py` 监听 `127.0.0.1:11450`，再转发到此端口。脚本使用本机正常 DNS 和路由，不自动选择某块 Wi-Fi 网卡，也不会把一个本来无法访问的网络变成可访问网络。

完整命令和分步说明见 [README.md](README.md)。遇到报错再读 [references/troubleshooting.md](references/troubleshooting.md)。

## 执行与验证

1. 在本地验证选定出口。直接网络方案用 `python scripts/local_forward.py`；代理软件方案用已有 HTTP 端口。监听和 SSH 窗口需要持续运行。
2. 在本地使用 `scripts/start_tunnel.ps1`，或生成 `ssh -N -T -p SSH_PORT -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 127.0.0.1:17891:127.0.0.1:LOCAL_PORT USER@HOST`。不要关闭 SSH 主机密钥验证；不要把密码写入文件。
3. 在服务器使用 `scripts/configure_remote.py` 写入代理环境文件。该脚本保留其他配置，变更前备份，并支持 `--dry-run`。`CODEX_HOME` 非默认时让 `--env-file` 指向对应目录。
4. 显式导出代理环境，或使用服务器端 `scripts/codex_with_proxy.py` 启动 Codex。不能假定任意版本会自动加载 `~/.codex/.env`；`config.toml` 不是 shell 环境文件，不凭空添加代理键。
5. 分别验证本地出口、服务器监听、服务器 `curl --proxy`、Codex 登录与一次实际请求。HTTP 401/403 可以表明已收到 HTTP 响应，但不能当成账号可用或完整 Codex 验证成功。不要把 `curl` 成功说成 Codex 已验证。
6. 报告实际完成的阶段、选定端口、保持运行的进程、备份路径和未完成项。没有真实服务器权限时只生成命令和本地验证证据，明确说明未进行远端验收。

用户只要求输出命令时，也附上本地出口、远端代理和 Codex 验收命令，并注明这些命令尚未执行；这样用户不会将隧道建立误当成整个链路可用。

## 运行边界与回滚

本地和远端只绑定回环地址，避免变成公开代理；服务器同一主机的其他用户仍可能访问回环监听。SSH 由本地发起，`-R` 监听在远端，右侧目标在本地解析。HTTPS/WSS 经 CONNECT 透明传输，由客户端验证 TLS。

仅改任务所需的代理变量，保留服务器 Codex 的认证、模型提供商、sandbox 和审批设置。不要复制本地 `auth.json`、API 密钥或 SSH 私钥到公开仓库。网络连通不代表账号或服务地区支持。

回滚时停止隧道和 Python 监听，按备份恢复环境文件，关闭带旧代理变量的 shell 或移除相关变量，重启 Codex。不要结束训练进程或删除其他用户配置。
