# 公网部署指南

把书籍解读器部署到公网服务器，分享给更多人使用。

## 一、服务器选型建议

| 方案 | 规格 | 参考价格 | 适用场景 | 注意事项 |
| --- | --- | --- | --- | --- |
| 阿里云 / 腾讯云 轻量应用服务器 | 2核4G | ¥50~100/月 | 推荐，国内访问快 | 需域名备案（约 1~2 周） |
| 境外 VPS（Vultr / 搬瓦工 / DigitalOcean） | 2核2G | $5~10/月 | 免备案，上线最快 | 国内访问延迟较高 |
| 家庭电脑 + 内网穿透（frp / Tailscale） | 任意 | 免费 | 只给熟人小范围用 | 不稳定、有安全风险，不建议公开 |

- 2核4G 足够支撑几十人同时使用；真正的成本瓶颈是 LLM API 费用，不是服务器。
- 选国内服务器务必先备案域名，否则 80/443 端口会被拦截。
- 预算敏感且用户在国内 → 轻量应用服务器；想当天上线 → 境外 VPS。

## 二、域名与 HTTPS

- 有域名体验更好：`book.example.com`。国内服务器必须用已备案域名。
- HTTPS 推荐用 **Caddy**（自动申请和续期证书，一行配置）：

```nginx
book.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

- 用 Nginx 时记得保留 `X-Forwarded-For` 头（服务已开启 `--proxy-headers`，限流按真实 IP 统计）：

```nginx
server {
    listen 80;
    server_name book.example.com;
    client_max_body_size 100m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 三、Docker 部署步骤

```bash
# 1. 克隆代码
git clone <你的仓库地址> && cd 书籍解读

# 2. 配置环境变量（.env 会被 docker-compose 读取）
cp .env.example .env
# 编辑 .env：填入 LLM_API_KEY、ACCESS_TOKEN（重要！公网必须设置口令）

# 3. 构建并启动
docker compose up -d --build

# 4. 验证
curl http://127.0.0.1:8000/
```

部署后访问 `http://<服务器IP>:8000`（或用域名反代），首次使用会要求输入访问口令。

### 常用运维命令

```bash
docker compose logs -f        # 查看日志
docker compose restart         # 重启
docker compose down            # 停止
docker compose up -d --build   # 更新代码后重新部署
```

## 四、成本控制

应用已内置三层保护，全部按 IP 统计（部署在反代后自动取真实 IP）：

1. **访问口令**（`ACCESS_TOKEN`）：页面需输入口令才能用，可随时修改（改 .env 重启即可）。
2. **每分钟限流**（`RATE_LIMIT_PER_MINUTE`，默认 30）：防止单 IP 刷请求。
3. **每日 LLM 额度**（`DAILY_LLM_LIMIT`，默认 100）：每个 IP 每天最多 100 次浓缩/讲解/问答，防止恶意消耗 API 费用。

另外，相同书籍、章节、比例的结果会走服务端缓存，多人重复操作不重复计费。

### 费用估算（以 DeepSeek 为例）

- DeepSeek 价格约：输入 ¥1/百万 token，输出 ¥2/百万 token（缓存命中价更低）。
- 一次 8 万字章节 25% 浓缩 ≈ 输出 2 万字 ≈ ¥0.04；讲解类似量级。
- 若每天 50 个活跃 IP × 平均 20 次操作 ≈ 1000 次 × ¥0.04 ≈ ¥40/天。**务必保留每日额度限制**，并按实际使用调低 `DAILY_LLM_LIMIT`。

## 五、安全注意事项

- `ACCESS_TOKEN` 务必设置一个足够随机的口令（建议 16 位以上），它直接保护你的 LLM 费用。
- 服务端不持久化上传的书籍内容（仅内存，重启即清空），适合分享；如需保存请自行扩展。
- 书籍版权：请只分享你有权传播的书籍，或明确告知使用者上传自己的电子书。
