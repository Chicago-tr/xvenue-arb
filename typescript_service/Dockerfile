FROM node:20-alpine

WORKDIR /app


COPY package*.json ./
RUN npm ci

COPY tsconfig.json ./

COPY drizzle.config.ts ./
COPY src/ ./src/


RUN npm run build


RUN npm ci --only=production


CMD ["npm", "start"]
