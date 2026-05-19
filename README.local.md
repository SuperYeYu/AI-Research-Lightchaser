# 🖥️ 本地部署与运行指南

本指南说明如何在本地部署、直接运行，以及如何配置 Windows 定时任务。

---

## 1. 环境要求

- Python `3.11+`
- 可以访问：
  - `arXiv`
  - `GitHub`
  - `Hugging Face`
  - `DeepSeek API`
  - 你的 SMTP 邮件服务器

检查 Python：

```powershell
python --version
```

---

## 2. 安装依赖

### 直接安装

```powershell
pip install -r requirements.txt
```

### 推荐：虚拟环境

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 3. 配置机密文件

复制模板：

```powershell
Copy-Item .\secrets.env.example .\secrets.env
```

然后编辑 `secrets.env`。

必须填写：

- `DEEPSEEK_API_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `MAIL_FROM`
- `MAIL_TO`

说明：

- `SMTP_PASSWORD` 往往应填写邮箱的 `SMTP 授权码`
- `MAIL_TO` 多个邮箱请用英文逗号分隔

---

## 4. 修改研究方向与抓取规模

编辑 [config.yaml](./config.yaml)。

### 当前关键参数

```yaml
report:
  lookback_hours: 24
  max_arxiv_fetch_results_per_profile: 200
  max_arxiv_candidates_per_profile: 100
  max_arxiv_results_per_profile: 20
  max_github_results: 15
  max_hf_results: 15
```

### 当前默认方向

- `graph`
- `agent`

如果要换方向，只需改 `profiles`。

---

## 5. 本地直接运行

### 只预览，不发邮件

```powershell
python .\scripts\run_daily_digest.py --dry-run --period daily
```

### 正式发送日报

```powershell
python .\scripts\run_daily_digest.py --period daily
```

### 正式发送周报

```powershell
python .\scripts\run_daily_digest.py --period weekly
```

---

## 6. 推荐发送时间

建议使用北京时间 `Asia/Shanghai`：

- 日报：每天 `20:00`
- 周报：每周日 `20:30`

---

## 7. Windows 定时运行

项目已附带：

- [run_daily_digest.ps1](./scripts/run_daily_digest.ps1)

### 手动运行脚本

日报：

```powershell
.\scripts\run_daily_digest.ps1 -Period daily
```

周报：

```powershell
.\scripts\run_daily_digest.ps1 -Period weekly
```

### Windows 任务计划程序

#### 日报任务

程序：

```text
powershell.exe
```

参数：

```text
-ExecutionPolicy Bypass -File "D:\...\ai_research_daily_digest\scripts\run_daily_digest.ps1" -Period daily
```

触发器建议：

- 每天 `20:00`

#### 周报任务

程序：

```text
powershell.exe
```

参数：

```text
-ExecutionPolicy Bypass -File "D:\...\ai_research_daily_digest\scripts\run_daily_digest.ps1" -Period weekly
```

触发器建议：

- 每周日 `20:30`

---

## 8. 输出文件

- HTML 预览：`output/`
- 运行缓存：`data/seen_cache.json`

---

## 9. 本地验证

```powershell
pytest -q tests
python -m compileall src scripts
```

---

## 10. 常见问题

### 抓取失败

优先检查：

- 当前网络
- 防火墙
- 代理

### 邮件发送失败

优先检查：

- SMTP 地址与端口
- SMTP 授权码
- 发件箱是否允许第三方 SMTP

### DeepSeek 调用失败

优先检查：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- 网络是否可访问 API
