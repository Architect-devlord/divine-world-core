# ~/dw_agent_project/dw_agent/electron/react-app/Dockerfile

FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine

WORKDIR /app

RUN npm install -g serve@14.2.1

COPY --from=builder /app/dist ./dist

EXPOSE 8765

CMD ["serve", "-s", "dist", "-l", "8765", "--no-port-switching"]