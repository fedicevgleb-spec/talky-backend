# client-build runs npm run build; /app/client/dist in the image is what Flask uses.
# If nginx serves files from the host (see nginx.conf root), run `make sync-dist` so
# host CLIENT_DIST matches the image, or copy /app/client/dist from a container.
FROM node:22-alpine AS client-build

WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY private ./private
COPY --from=client-build /client/dist ./client/dist

EXPOSE 4242

CMD ["python", "app.py"]
