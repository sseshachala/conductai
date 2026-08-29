# Build context is REPO ROOT (see .github/workflows/container-security.yml).
# apps/web/src/app/(marketing)/docs/page.tsx imports docs/reference/*.md via
# ../../../../../../docs/... — needs the repo-root docs/ dir in the build tree.
FROM node:20-alpine AS base
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm install

FROM base AS dev
COPY apps/web/ .
COPY docs/ /docs/
CMD ["npm", "run", "dev"]

FROM base AS builder
COPY apps/web/ .
COPY docs/ /docs/
RUN npm run build

FROM node:20-alpine AS prod
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
CMD ["node", "server.js"]
