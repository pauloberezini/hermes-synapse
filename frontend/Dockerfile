# Stage 1: Build Vite React application
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# Stage 2: Serve application using Nginx
FROM nginx:alpine

# Copy built assets from build stage to nginx default public directory
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx proxy config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose Nginx port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
