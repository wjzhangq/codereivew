# ===========================================================================
# 前端多阶段构建 —— node:build → nginx:serve
#   - 依赖层:package.json + lockfile → npm ci(可复现)
#   - 源码层:COPY 源码 → build
#   - 运行层:nginx + dist 静态产物
# ===========================================================================

FROM node:20-alpine AS build
WORKDIR /app
# 单独复制依赖清单 → 代码改动不重装依赖
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
# 源码层
COPY frontend/ ./
RUN npm run build

# --- 运行阶段 ------------------------------------------------------------ #
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
