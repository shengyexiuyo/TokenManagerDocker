# TokenManager Docker 版（NAS 部署）

这是 TokenManager 的 Docker 容器化版本，功能与原版**完全一致**：

- ✅ Web GUI 界面（daisyUI，已内置全部前端资源，**内网无外网也能正常显示**）
- ✅ 查询各 AI 平台 token 余额、一键查询所有余额
- ✅ 用量统计（官方 API 支持的平台）
- ✅ 保存、删除、复制 token（持久化存储，容器重建不丢失）
- ✅ **自定义服务商**：服务商列表最后一栏"自定义"，支持添加多个 OpenAI 兼容中转站（one-api/new-api 常规计费接口），支持新增、修改、删除
- ✅ **实时价格**：右侧最后一栏展示 traktoken.com 的实时价格表（按性价比降序，美元/百万tokens），并为存在峰谷定价的服务商（如 DeepSeek）标明当前是峰还是谷时段
- ✅ 界面中英文双语（默认中文，右上角一键切换）

支持的服务商：deepseek / openai(GPT) / doubao / qwen / tencent / GLM / mimo / kimi / claude / gemini / meta / minimax / custom(自定义)

> 说明：Gemini / Meta / MiniMax 官方不提供余额查询 API，查询结果为 Key 有效性验证 + 可用模型数；Gemini/Meta 查询需要能访问相应网络的代理环境。实时价格来自 traktoken.com，服务端缓存10分钟。

## 📁 目录结构

```
TokenManagerDocker/
├── app/                    # 应用代码（server.py + token_core.py + gui/）
│   └── gui/vendor/         # 已本地化的前端资源（tailwind/daisyUI）
├── data/                   # 密钥持久化目录（挂载卷，运行时自动生成 .XX_key 文件）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 🚀 方式一：docker compose 部署（推荐）

把整个 `TokenManagerDocker` 文件夹上传到 NAS（如 `/volume1/docker/TokenManagerDocker`），然后 SSH 执行：

```bash
cd /volume1/docker/TokenManagerDocker
docker compose up -d --build
```

浏览器访问：**http://NAS的IP:8888**

## 🚀 方式二：docker run 部署

```bash
cd /volume1/docker/TokenManagerDocker
docker build -t token-manager:latest .
docker run -d \
  --name token-manager \
  --restart unless-stopped \
  -p 8888:5000 \
  -v /volume1/docker/TokenManagerDocker/data:/data \
  token-manager:latest
```

## 🚀 方式三：群晖 DSM（Container Manager）

1. 用 File Station 把 `TokenManagerDocker` 文件夹上传到 docker 共享文件夹
2. 打开 Container Manager → 项目 → 新增 → 选择"使用已有的 docker-compose.yml"（路径指向刚上传的文件夹）
3. 一路下一步并启动，访问 `http://NAS的IP:8888`

威联通 Container Station、Unraid 等同理（导入 docker-compose.yml 或按方式二填参数）。

## ⚙️ 配置说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 外部端口 | `8888` | 修改 docker-compose.yml 中 `"8888:5000"` 左边的数字。群晖 DSM 管理界面占用 5000，不要映射到 5000 |
| 数据目录 | `./data` | 密钥文件（`.XX_key`）保存在这里，务必保留这个挂载，否则容器重建后密钥丢失 |
| DATA_DIR | `/data` | 容器内数据目录，配合上面的挂载使用，一般无需修改 |
| ACCESS_CODE | 空 | **访问码**。设置后打开界面和所有 API 都要求先输入访问码；留空则不启用鉴权 |
| SESSION_DAYS | `30` | 登录有效期（天），有效期内打开页面免输访问码；`0` 表示关闭浏览器后即需重新登录 |

## 🔒 访问码

部署在公网或家庭内网后，任何人知道 IP 就能打开界面。设置访问码后：

- 首次打开页面会先进入访问验证页（与主界面同风格），输入正确访问码才能进入
- 未通过验证时，**所有 API（余额查询、密钥读取/保存）都会被服务端拒绝**，无法绕过界面直接调接口
- 验证通过后 30 天内免输入（存在浏览器 Cookie 中，可通过 `SESSION_DAYS` 调整），也可随时点界面右上角"退出登录"
- 修改访问码后，所有已登录的会话立即失效

**启用方法**：编辑 docker-compose.yml，把 `- ACCESS_CODE=` 改成 `- ACCESS_CODE=你的访问码`，然后：

```bash
docker compose up -d
```

（首次启用因为代码更新需要 `docker compose up -d --build` 重新构建一次，之后仅改访问码只需 `up -d`）

**忘记访问码**：docker-compose.yml 里查看或修改，`docker compose up -d` 重启即可。

## 🔧 常用命令

```bash
docker compose logs -f          # 查看日志
docker compose restart          # 重启
docker compose down             # 停止并删除容器（data目录中的密钥保留）
docker compose up -d --build    # 更新代码后重新构建并启动
```

## ❓ 构建一直卡在 Pulling（国内网络）

构建镜像时需要先拉取基础镜像 `python:3.11-slim`，而 Docker Hub 在国内无法直连，所以会永远卡在 Pulling。三种解决办法：

**办法1（已内置，推荐）**：本项目的 Dockerfile 已改为默认从国内加速站拉取基础镜像（`docker.1ms.run`，实测可用），并给 pip 装依赖配了阿里云源（清华源对部分网络会403）。直接用最新的 Dockerfile 重新构建即可：

```bash
docker compose down
docker compose up -d --build
```

如果基础镜像站失效，打开 Dockerfile 把 `ARG PYTHON_BASE=` 那行换成注释里的备选地址（如 `docker.m.daocloud.io/library/python:3.11-slim`）再重新构建；如果 pip 报 403/超时，把第 18 行 `-i` 后面的地址换成 `https://pypi.tuna.tsinghua.edu.cn/simple` 或 `https://mirrors.cloud.tencent.com/pypi/simple/` 换个源重试。

> 日志开头的 `token-manager Warning Get https://registry-1.docker.io/v2/...` 可忽略——那是面板尝试去 Docker Hub 拉取项目镜像名的提示，compose 里已配置 `pull_policy: build` 只构建不拉取，不影响实际构建。

**办法2：给飞牛 Docker 配置加速源**（对所有项目都生效）

1. 打开飞牛 fnOS 的 **Docker** 应用 → 左侧 **镜像仓库** → **设置 → 加速源设置**
2. 添加以下加速地址（多加几个互为备份，把可用的置顶）：
   - `https://docker.1ms.run`
   - `https://docker.m.daocloud.io`
3. 保存后**重启 Docker 服务**，再重新构建

⚠️ 飞牛有已知问题：界面里改加速源可能没有真正写入配置。SSH 登录 NAS 执行 `docker info | grep -A 3 Mirrors` 检查是否生效；若没生效，手动编辑 `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": ["https://docker.1ms.run", "https://docker.m.daocloud.io"]
}
```

然后执行 `sudo systemctl restart docker`，重新构建。

**办法3：电脑上构建好再搬到 NAS**（NAS 实在拉不动时的兜底，见下文提示）

## 💡 提示

- NAS 性能较弱、构建镜像慢的话，可以在电脑上执行 `docker build -t token-manager:latest .` 后用 `docker save token-manager:latest -o token-manager.tar` 导出，拷到 NAS 用 `docker load -i token-manager.tar` 导入，再按方式二运行（去掉 build 步骤）。
- Mimo 平台比较特殊：余额接口需要浏览器登录后的 Cookie（约24小时有效），不是 API Key，详见原项目说明。
- 界面中保存的密钥会即时写入 `data/` 目录，可直接备份该目录。
