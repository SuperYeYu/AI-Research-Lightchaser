# ☁️ GitHub Actions 自动化部署指南

本指南说明如何把项目部署到 GitHub，并通过 GitHub Actions 自动生成并发送日报 / 周报。

---

## 1. 适用场景

适合：

- 想每天自动发送
- 不想依赖本地电脑开机
- 希望别人 fork 后也能快速使用

不太适合：

- 不想把 API / SMTP 凭据放进 GitHub Secrets
- 邮箱服务对云端 SMTP 登录限制很严格

---

## 2. 部署思路

GitHub Actions 会定时执行：

```powershell
python scripts/run_daily_digest.py --period daily
```

或者：

```powershell
python scripts/run_daily_digest.py --period weekly
```

---

## 3. 新建 GitHub 仓库

把交付目录整体上传到 GitHub 仓库，例如：

```text
ai-research-daily-digest
```

---

## 4. 配置 GitHub Secrets

进入：

`Settings -> Secrets and variables -> Actions`

新建以下 `Repository secrets`：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `MAIL_FROM`
- `MAIL_TO`

说明：

- `SMTP_PASSWORD` 建议使用 SMTP 授权码
- `DEEPSEEK_MODEL` 推荐 `deepseek-v4-flash`

---

## 5. 工作流文件

项目已附带：

- [daily-digest.yml](./.github/workflows/daily-digest.yml)

你只需提交到仓库即可。

---

## 6. 推荐发送时间

建议使用北京时间 `Asia/Shanghai`：

- 日报：`20:00`
- 周报：每周日 `20:30`

GitHub Actions 使用 UTC cron，因此工作流中已换算为：

- 日报：`0 12 * * *`
- 周报：`30 12 * * 0`

---

## 7. 手动触发

在 GitHub 页面：

`Actions -> AI Research Daily Digest -> Run workflow`

然后选择：

- `daily`
- `weekly`

---

## 8. 快速改方向

直接修改：

- [config.yaml](./config.yaml)

重点改：

- `profiles`
- `keywords`
- `queries`

---

## 9. 快速换 API / 模型

只需要改 GitHub Secrets：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`

不用改代码。

---

## 10. 注意事项

### 邮箱限制

有些邮箱会限制来自 GitHub Actions 云端机器的 SMTP 登录。

如果遇到发信失败，可以：

- 改用更稳定的 SMTP 服务
- 或改回本地定时运行

### 外部站点波动

以下站点都会偶尔出现波动：

- arXiv
- GitHub
- Hugging Face

这属于自动抓取类项目的正常维护范围。

