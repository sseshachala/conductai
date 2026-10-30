# Build context is REPO ROOT (see .github/workflows/container-security.yml).
# The web app is an npm workspace: the only lockfile is the root
# package-lock.json, so install from the workspace root with `npm ci`.
# Installing from apps/web/package.json alone resolves the tree unlocked
# (and crashes npm's arborist), so images neither built nor matched what ships.
#
# The repo layout is kept inside the image (/app/apps/web, /app/docs,
# /app/config) so these relative imports resolve unchanged:
#   - apps/web/src/app/(marketing)/docs/page.tsx → ../../../../../../docs/*.md
#   - tsconfig alias @config/* → ../../config/*
FROM node:20-alpine AS base
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
RUN npm ci --workspace apps/web --include-workspace-root

FROM base AS dev
COPY apps/web/ apps/web/
COPY docs/ docs/
COPY config/ config/
WORKDIR /app/apps/web
CMD ["npm", "run", "dev"]

FROM base AS builder
COPY apps/web/ apps/web/
COPY docs/ docs/
COPY config/ config/
WORKDIR /app/apps/web
RUN npm run build

FROM node:20-alpine AS prod
WORKDIR /app
ENV NODE_ENV=production
# Standalone output mirrors the workspace layout (tracing root = /app).
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public
CMD ["node", "apps/web/server.js"]
