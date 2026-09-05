# TokenManager Docker 版

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
├── .github/workflows/      # GitHub Actions：推送代码自动构建并发布镜像到 GHCR
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 🚀 方式一：单文件 compose 部署（推荐，无需克隆源码）

只需要一个 `docker-compose.yml` 文件。在 NAS 上新建一个目录（如 `/volume1/docker/token-manager`），在里面创建 `docker-compose.yml`，粘贴以下内容（**把 `<你的GitHub用户名>` 换成实际用户名**）：

```yaml
services:
  token-manager:
    image: ghcr.io/<你的GitHub用户名>/tokenmanagerdocker:latest
    container_name: token-manager
    restart: unless-stopped
    ports:
      # 左边是外部访问端口，右边是容器内端口(勿改)
      # 群晖DSM默认占用5000端口，故外部默认使用8888，浏览器访问 http://NAS_IP:8888
      - "8888:5000"
    environment:
      - DATA_DIR=/data
      - TZ=Asia/Shanghai
      # 访问码：设置后打开界面和所有API都要求先输入；留空则不启用鉴权
      - ACCESS_CODE=
      # 登录有效期（天）；0=关闭浏览器后即需重新登录
      - SESSION_DAYS=30
    volumes:
      # 密钥等配置持久化到当前目录的data文件夹，容器更新重建后不丢失
      - ./data:/data
```

然后启动：

```bash
cd /volume1/docker/token-manager
docker compose up -d
```

浏览器访问：**http://NAS的IP:8888**（建议按下面"配置说明"先设置访问码）。

镜像已构建为 **amd64 + arm64 双架构**，x86 和 ARM 的 NAS 都可以直接用。首次启动会拉取约 200MB 的镜像，之后离线也能正常重启。

**国内拉取镜像卡住/失败**：Docker 的加速源配置（registry-mirrors）只对 Docker Hub 生效，对 ghcr.io 无效。把 compose 里的 `image` 换成加速站的 ghcr 代理地址即可，例如（以 DaoCloud 为例，其他加速站同理把 `ghcr.io` 换成其代理域名）：

```yaml
image: ghcr.m.daocloud.io/<你的GitHub用户名>/tokenmanagerdocker:latest
```

## 🚀 方式二：克隆仓库部署

想保留源码或方便查看代码的话，克隆整个仓库，一样直接拉预构建镜像：

```bash
git clone https://github.com/<你的GitHub用户名>/TokenManagerDocker.git
cd TokenManagerDocker
# 先把 docker-compose.yml 里的 <你的GitHub用户名> 替换成实际用户名
docker compose up -d
```

## 🚀 方式三：群晖 DSM（Container Manager）

1. 在 File Station 的 docker 共享文件夹里新建 `token-manager` 目录，放入编辑好的 `docker-compose.yml`（内容同方式一，可把加速站 image 一并换好）
2. 打开 Container Manager → 项目 → 新增 → 选择"使用已有的 docker-compose.yml"（路径指向刚建的目录）
3. 一路下一步并启动，访问 `http://NAS的IP:8888`

威联通 Container Station、Unraid、飞牛 fnOS 等同理（导入 docker-compose.yml 即可）。

## 🚀 方式四：从源码本地构建（改代码或镜像拉不动时）

克隆仓库后，把 `docker-compose.yml` 里 `image:` 那行注释掉，取消 `build:` 两行注释，然后：

```bash
docker compose up -d --build
```

Dockerfile 已内置国内加速：基础镜像默认从 `docker.1ms.run` 拉取，pip 走阿里云源。加速站失效时按 Dockerfile 内注释换备选地址。NAS 构建太慢的兜底办法：在电脑上 `docker build -t token-manager:latest .` 后用 `docker save` 导出 tar，拷到 NAS `docker load` 导入。

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

**启用方法**：编辑 docker-compose.yml，把 `- ACCESS_CODE=` 改成 `- ACCESS_CODE=你的访问码`，然后 `docker compose up -d` 即可生效。

**忘记访问码**：docker-compose.yml 里查看或修改，`docker compose up -d` 重启即可。

## 🔧 常用命令

```bash
docker compose logs -f                      # 查看日志
docker compose restart                      # 重启
docker compose down                         # 停止并删除容器（data目录中的密钥保留）
docker compose pull && docker compose up -d # 更新到最新版镜像
```

## 🛠️ 维护者：镜像发布流程

镜像通过 GitHub Actions 自动构建发布（`.github/workflows/docker-publish.yml`），无需手动操作：

- **自动构建**：推送代码到默认分支（main/master）→ 自动构建 amd64/arm64 双架构镜像并发布为 `ghcr.io/<用户名>/tokenmanagerdocker:latest`
- **版本发布**：打标签 `git tag v1.0.0 && git push --tags` → 额外生成 `v1.0.0` 版本 tag 的镜像
- **⚠️ 首次发布后必做**：GitHub 仓库页 → 右侧 **Packages** → 点进 `tokenmanagerdocker` → **Package settings** → **Danger Zone → Change visibility → Public**。GHCR 包默认是 Private，不改为 Public 别人拉取会报 `denied`
- CI 构建使用官方基础镜像 `python:3.11-slim`（通过 build-args 覆盖），本地 NAS 构建才走 Dockerfile 里默认的国内加速站

## ❓ 从源码构建时卡在 Pulling（仅方式四需要看）

从源码构建需要先拉取基础镜像 `python:3.11-slim`，而 Docker Hub 在国内无法直连，会永远卡在 Pulling。三种解决办法：

**办法1（已内置，推荐）**：本项目的 Dockerfile 已改为默认从国内加速站拉取基础镜像（`docker.1ms.run`，实测可用），并给 pip 装依赖配了阿里云源（清华源对部分网络会403）。直接重新构建即可：

```bash
docker compose down
docker compose up -d --build
```

如果基础镜像站失效，打开 Dockerfile 把 `ARG PYTHON_BASE=` 那行换成注释里的备选地址（如 `docker.m.daocloud.io/library/python:3.11-slim`）再重新构建；如果 pip 报 403/超时，把 `RUN pip install` 里 `-i` 后面的地址换成 `https://pypi.tuna.tsinghua.edu.cn/simple` 或 `https://mirrors.cloud.tencent.com/pypi/simple/` 换个源重试。

**办法2：给 NAS 的 Docker 配置加速源**（对所有项目都生效）

1. 打开 NAS 的 Docker 管理界面 → 镜像仓库/注册表 → 设置 → 加速源设置
2. 添加以下加速地址（多加几个互为备份，把可用的置顶）：
   - `https://docker.1ms.run`
   - `https://docker.m.daocloud.io`
3. 保存后**重启 Docker 服务**，再重新构建

⚠️ 部分系统（如飞牛）有已知问题：界面里改加速源可能没有真正写入配置。SSH 登录 NAS 执行 `docker info | grep -A 3 Mirrors` 检查是否生效；若没生效，手动编辑 `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": ["https://docker.1ms.run", "https://docker.m.daocloud.io"]
}
```

然后执行 `sudo systemctl restart docker`，重新构建。

**办法3：电脑上构建好再搬到 NAS**（NAS 实在拉不动时的兜底，见方式四末尾）

> 日志开头的 `token-manager Warning Get https://registry-1.docker.io/v2/...` 可忽略——那是面板尝试去 Docker Hub 拉取项目镜像名的提示，不影响实际使用。

## 💡 提示

- Mimo 平台比较特殊：余额接口需要浏览器登录后的 Cookie（约24小时有效），不是 API Key，详见原项目说明。
- 界面中保存的密钥会即时写入 `data/` 目录，可直接备份该目录（密钥文件不会进入 git 仓库）。
