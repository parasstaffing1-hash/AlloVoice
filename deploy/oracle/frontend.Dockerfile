# AlloVoice frontend (production): standard Next.js server, no Cloudflare adapter.
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .
# NEXT_PUBLIC_* is baked at build time — pass via --build-arg.
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

EXPOSE 3000
ENV PORT=3000
CMD ["npm", "run", "start", "--", "-p", "3000"]
