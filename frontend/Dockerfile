FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Per-device config: which vehicle this terminal is mounted in, and whether it is an operator or admin build
ARG VITE_VEHICLE_ID=
ARG VITE_APP_MODE=both
ENV VITE_VEHICLE_ID=$VITE_VEHICLE_ID VITE_APP_MODE=$VITE_APP_MODE
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
