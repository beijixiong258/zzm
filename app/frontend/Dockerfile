FROM node:26-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --include=dev --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:26-bookworm-slim
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY static-server.mjs ./
USER node
EXPOSE 5173
CMD ["node", "static-server.mjs"]
