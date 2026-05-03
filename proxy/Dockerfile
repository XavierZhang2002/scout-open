FROM node:23-alpine

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apk add --no-cache supervisor

# 安装pnpm
RUN npm install -g pnpm


# 复制claude-code-router文件
COPY claude-code-router/ /app/claude-code-router/
WORKDIR /app/claude-code-router
# 设置CI环境变量以避免交互式提示
ENV CI=true
RUN pnpm install --frozen-lockfile
WORKDIR /app

# 复制配置文件
COPY .claude-code-router/ /root/.claude-code-router/
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# 创建目录并复制Docker专用配置

# 设置权限
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 暴露端口
EXPOSE 3456

# 启动命令
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]