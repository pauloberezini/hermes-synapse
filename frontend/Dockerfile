# Stage 1: Build Vite React application
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# Stage 2: Serve application using Nginx (unprivileged, port 8080)
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN mkdir -p /var/cache/nginx /var/run /run /var/log/nginx \
    && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/run /run /var/log/nginx \
    && sed -i '/^user /d' /etc/nginx/nginx.conf \
    && sed -i 's|pid .*|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf

USER nginx

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
