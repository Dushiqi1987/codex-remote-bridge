# 验证记录

核对日期：2026-10-12。

- `python -m unittest discover -s tests -v`：11 项本地测试全部通过。
- `python -X utf8 <skill-creator>/scripts/quick_validate.py ./codex-remote-bridge`：`Skill is valid!`。
- `start_tunnel.ps1 -ServerHost gpu.example.com -SshPort 23001 -LocalPort 7890 -DryRun`：生成回环监听 `17891` → 本地 HTTP `7890` 的正确 SSH 命令，没有连接服务器。
- 所有源码和文档可按 UTF-8 解码；使用中文的 Windows 环境运行 skill 校验器时显式开启 Python UTF-8 模式。

协议测试覆盖 GET 查询串、POST 请求体、分块请求、流式响应即时转发、CONNECT 二进制与首包缓冲、半关闭、HTTP WebSocket Upgrade、IPv6 CONNECT 地址解析、无效请求和上游连接失败，以及配置备份、保留其他环境设置、重复执行、预览不写文件和启动器不执行环境文件内容。

两个独立使用场景检查：本地 HTTP 代理软件，以及本地直接网络且默认端口占用。代理软件场景的初次命令输出遗漏验收命令，已在 SKILL.md 补充命令输出时保留分层验收的提醒；修订后的行为未再次用独立代理复测。Wi-Fi 场景的无 skill 基线受账号使用额度限制未完成，因此未声称完整行为基准对比通过。

限制：没有连接真实 GPU 服务器，没有验证 SSH 服务端权限、TLS/WSS 真实服务握手、Codex 账号登录或模型实际回复。CONNECT 测试验证的是透明传输；HTTP Upgrade 测试验证的是升级后字节转发，不是完整 WebSocket 协议实现。本地测试通过不能代替部署后的逐层验收。
