# codex-register-py

基于 Python 的 HTTP 自动化脚本，按当前代码实现通过接口流程执行账号注册/登录相关步骤，并通过 MailAPI 轮询邮箱验证码。

## 免责声明

请仅在你有明确授权、并且符合目标平台条款与当地法律法规的前提下使用本项目。由不当使用产生的风险与责任由使用者自行承担。项目仅供参考学习，请勿滥用！！！

## 项目结构

```text
api_register.py      # 主流程：并发执行、验证码轮询、结果保存、上传
mailapi.py           # MailAPI 封装：查询邮件并提取 6 位验证码
proxy_cache.json     # 代理缓存（可选）
tokens/              # 生成结果目录（自动创建）
requirements.txt     # Python 依赖列表
README.md
```

## 运行环境

- Python 3.10+
- Windows / Linux / macOS

## 安装依赖

使用 `requirements.txt` 一键安装：

```bash
pip install -r requirements.txt
```

等价依赖为：`curl_cffi`、`requests`、`PySocks`。

说明：
- `curl_cffi`：主注册流程 HTTP 会话及浏览器指纹模拟。
- `requests`：MailAPI 与上传逻辑、代理测试逻辑。
- `pysocks`：`requests` 使用 socks4/socks5 代理时需要。

## 配置说明

在 `api_register.py` 中配置以下常量（当前已脱敏为占位值）：

```python
EMAIL_DOMAINS = ["example1.com", "example2.com", "example3.com", "example4.com"]
CPA_URL = "http://your-server:port"
MANAGEMENT_KEY = "your-management-key"
MAIL_API_URL = "https://mail.example.com"
MAIL_API_AUTH = "your-mailapi-auth"
```

字段说明：
- `EMAIL_DOMAINS`：随机邮箱域名池。
- `MAIL_API_URL` / `MAIL_API_AUTH`：cloudflare_temp_email邮件查询服务地址和管理密码，默认没有启用私有站点，如果启用了私有站点请填写`MAIL_PASSWD`。
- `CPA_URL` / `MANAGEMENT_KEY`：token 文件上传的CPA服务地址和登陆密钥。

域名邮箱服务项目：
- `cloudflare_temp_email`：https://github.com/dreamhunter2333/cloudflare_temp_email

## 使用方式

在项目目录执行：

```bash
python api_register.py
```

参数：
- `--count`：本次处理数量，默认 `5`。
- `--workers`：并发线程数，默认 `1`。

示例：

```bash
python api_register.py --count 1 --workers 1
python api_register.py --count 20 --workers 5
```

## 运行流程（按当前代码）

1. 随机生成邮箱与密码。
2. 从 `proxy_cache.json` 读取可用代理（若为空则直连）。
3. 执行 OAuth/OTP/账号信息提交流程。
4. 通过 `MailAPI` 轮询验证码并校验。
5. 将结果保存到 `tokens/*.json`。
6. 若成功条目大于 0，则调用上传接口并在上传成功后删除本地文件。

## 输出说明

- 日志文件：`api_register.log`
- token 结果：`tokens/<email>--<password>.json`
- 统计输出：成功数、失败数、总耗时

## 代理池说明

`api_register.py` 只负责读取 `proxy_cache.json` 并随机使用。

缓存规则（按当前代码）：
- 以 UTC 日期 (`YYYY-MM-DD`) 作为缓存时间标记。
- 若缓存中的 `date` 与当前日期不一致，会先删除旧 `proxy_cache.json`，再重建当天缓存。
个人代理池构建脚本就不上传到仓库了，如果没有合适的代理，可用使用本人的另一个项目（还没上传）

## 常见问题

1. MailAPI 查询失败
- 检查 `MAIL_API_URL` 与 `MAIL_API_AUTH` 是否有效。
- 确认网络可达、接口路径可访问。

2. 代理可用但注册失败率高
- 降低并发（`--workers`）。
- 清理并重新生成 `proxy_cache.json`。

3. 上传失败
- 检查 `CPA_URL` 与 `MANAGEMENT_KEY`。
- 检查上传接口路径是否与服务端一致。


