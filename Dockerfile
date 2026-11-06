# 前端构建与运行。
FROM node:26-bookworm-slim AS frontend-build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --include=dev --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:stable-alpine AS frontend
COPY --from=frontend-build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 5173

# 安装后端直接使用的 QMD 官方命令行工具。
FROM node:22-bookworm-slim AS qmd-runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates python3 make g++ cmake && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/qmd
COPY retrieval/package*.json ./
RUN npm ci --omit=dev

# 后端构建与运行；最后一个阶段保留为默认后端镜像。
FROM maven:3.9-eclipse-temurin-17 AS backend-build
WORKDIR /build
COPY pom.xml ./
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:17-jre AS backend
RUN apt-get update && apt-get install -y --no-install-recommends curl fontconfig fonts-noto-cjk libgomp1 libstdc++6 && rm -rf /var/lib/apt/lists/*
ENV JAVA_TOOL_OPTIONS="-Djava.awt.headless=true"
ENV PATH="/opt/qmd/node_modules/.bin:${PATH}" HOME=/home/aicademiya \
    INDEX_PATH=/data/index.sqlite QMD_CONFIG_DIR=/data/config XDG_CACHE_HOME=/data/cache
WORKDIR /app
COPY --from=qmd-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=qmd-runtime /opt/qmd /opt/qmd
COPY --from=backend-build /build/target/aicademiya-server.jar ./app.jar
RUN useradd --create-home --uid 10001 aicademiya && mkdir -p /app/data/uploads /app/data/recycle /data && chown -R aicademiya:aicademiya /app /data
USER aicademiya
EXPOSE 8001
CMD ["java", "-jar", "app.jar"]
