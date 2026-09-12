FROM node:20-bookworm-slim
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/
RUN npm ci
COPY apps/web/src ./apps/web/src
COPY apps/web/public ./apps/web/public
COPY apps/web/next.config.js apps/web/next-env.d.ts apps/web/tsconfig.json apps/web/tailwind.config.ts apps/web/postcss.config.js ./apps/web/
COPY docs ./docs
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_API_URL=/api NEXT_TELEMETRY_DISABLED=1
RUN ln -s ../../package-lock.json apps/web/package-lock.json
RUN npm run build --workspace apps/web
USER node
WORKDIR /repo/apps/web
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
