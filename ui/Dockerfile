FROM node:20-alpine

WORKDIR /app

# Install deps first (better layer caching)
COPY ui/package*.json ./
RUN npm ci

# Copy UI source (build context is repo root, so prefix with ui/)
COPY ui/ .

# NEXT_PUBLIC_* vars are inlined at build time — pass via --build-arg
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

ENV PORT=3001

EXPOSE 3001

CMD ["npm", "start"]
