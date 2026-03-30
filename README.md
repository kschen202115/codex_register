# codex-register-py

基于 Python 的 HTTP 自动化脚本，通过接口执行账号注册/登录相关步骤，并通过 MailAPI 轮询邮箱验证码，注册完成后自动上传到CPA（如果有配置的话）。
项目参考：https://github.com/Ethan-W20/openai-auto-register

本项目依旧可用，如无法注册请自行检查代理质量和对应域名邮箱是否被拉黑

**官方已经拉闸，现在注册的账号基本无法存活超过3天，甚至之前注册的账号也存在被连坐的可能，还有就是不要登太猛，不要把额度短时间内用完**

**官方已经拉闸，新代码正在测试，暂时不打算公开，算是我最初思路的升级版吧，代码量减少了很多，可能算是利用漏洞吧，哎太难了**

# 当前已经修复了，上传了一版代码，用的是比较通用的PoW
**这个不是我的最初思路，但是看到已经有佬在论坛中讲解了PoW的思路，那我也就发出来吧**

现在之前再获取sentinel的时候缺少PoW，导致要求添加手机号码。同时现在直接注册会无法获取的到完整的内容，需要再次登陆才可以。感觉这个很快也会被堵住，且用且珍惜吧

**我怀疑PoW的是openai的钓鱼方式，我带上PoW注册的基本上活不了多久就g了**

直接在codex上进行注册会被要求添加手机号码，据说如果ip够干净能跳过，但是干净的ip是用一个少一个。

不添加手机号且不用PoW的方式也弄出来了，但是不太想很快公开，先等等看吧。下图为不需要手机号不用PoW的截图

<img width="575" height="163" alt="image" src="https://github.com/user-attachments/assets/06915722-1caf-4a80-922b-2471c019ce42" />


## 免责声明

请仅在你有明确授权、并且符合目标平台条款与当地法律法规的前提下使用本项目。由不当使用产生的风险与责任由使用者自行承担。项目仅供参考学习，请勿滥用！！！

## 项目结构

```text
codex_register.py      # 主流程：并发执行、验证码轮询、结果保存、上传
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

在 `codex_register.py` 中配置以下常量：

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
python codex_register.py
```

参数：
- `--count`：本次处理数量，默认 `5`。
- `--workers`：并发线程数，默认 `1`。

示例：

```bash
python codex_register.py --count 1 --workers 1
python codex_register.py --count 20 --workers 5
```
<img width="889" height="482" alt="image" src="https://github.com/user-attachments/assets/323147d4-65d1-4cfd-8d9b-b5fcaee6f010" />

`本地网络太差了，请求一个网址要好久，如果部署再云端的话会快不少，单线程平均1-3s一个账号`

## 运行流程（按当前代码）

1. 随机生成邮箱与密码。
2. 从 `proxy_cache.json` 读取可用代理（若为空则直连）。
3. 执行 OAuth/OTP/账号信息提交流程。
4. 通过 `MailAPI` 轮询验证码并校验。
5. 将结果保存到 `tokens/*.json`。
6. 若成功条目大于 0，则调用上传接口并在上传成功后删除本地文件。

## 输出说明

- 日志文件：`codex_register.log`
- token 结果：`tokens/<email>--<password>.json`
- 统计输出：成功数、失败数、总耗时

## 代理池说明

`codex_register.py` 只负责读取 `proxy_cache.json` 并随机使用。

缓存规则（按当前代码）：
- 以 UTC 日期 (`YYYY-MM-DD`) 作为缓存时间标记。
- 若缓存中的 `date` 与当前日期不一致，会先删除旧 `proxy_cache.json`，再重建当天缓存。
- 个人代理池构建脚本就不上传到仓库了，如果没有合适的代理，可用使用本人的另一个项目（[warp-proxy-docker](https://github.com/kschen202115/warp-proxy-docker)）
- 上面那个仓库有问题，酌情使用，或者使用这个仓库的公共代理[PROXY-List](https://github.com/TheSpeedX/PROXY-List)

`proxy_cache.json`内结构如下
```bash
{
    "date": "2026-03-10",//更新时间
    "usable": [//可用列表
        {
            "proxy": "127.0.0.1:1080",//地址：端口和可用的协议
            "http": false,
            "socks4": false,
            "socks5": true
        }
    ]
}
```
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


