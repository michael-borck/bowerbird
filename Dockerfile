# Bowerbird self-host image: server + built web UI in one container (ADR-0008).
FROM node:22-alpine AS build
WORKDIR /app
# The desktop workspace pulls in Electron; its binary is useless in a
# server image, so skip the download.
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1
COPY . .
RUN npm install && npm run build -w @michaelborck/bowerbird-core -w @michaelborck/bowerbird-server && npm run build -w @michaelborck/bowerbird-web

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json ./
COPY --from=build /app/packages/core/package.json packages/core/
COPY --from=build /app/packages/core/dist packages/core/dist
COPY --from=build /app/packages/server/package.json packages/server/
COPY --from=build /app/packages/server/dist packages/server/dist
COPY --from=build /app/packages/web/dist packages/server/public
RUN npm install --omit=dev
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD wget -qO- http://localhost:3000/api/health || exit 1
CMD ["node", "packages/server/dist/index.js"]
