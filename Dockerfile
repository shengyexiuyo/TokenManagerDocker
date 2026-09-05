# Token Manager - NAS Docker部署版（国内网络优化）

# 基础镜像默认走国内加速站：Docker Hub国内直连会一直卡在Pulling
# 如该站失效，取消下面备选注释换一个即可；海外网络或已配置镜像加速可改回 python:3.11-slim
ARG PYTHON_BASE=docker.1ms.run/library/python:3.11-slim
# 备选：docker.m.daocloud.io/library/python:3.11-slim
# 备选：python:3.11-slim
FROM ${PYTHON_BASE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先安装依赖，利用Docker层缓存（pip走阿里云源；清华源对部分网络403，如阿里云也异常可换回清华源）
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 复制应用代码（含已本地化的GUI静态资源，内网也可正常显示界面）
COPY app/ .

# 密钥等持久化数据目录
RUN mkdir -p /data
ENV DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 5000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/api/providers', timeout=4).status==200 else 1)"

CMD ["python", "server.py"]
