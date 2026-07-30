# celegans-sim, as a static site.
#
# There is no simulation server in this image. The animal runs in the visitor's browser --
# `web/worm.wasm` is the step functions and `web/worm.model` is everything Python
# precomputed once (see tools/export_model.py). So this container serves files and nothing
# else: CPU is the visitor's, and one instance scales to as many people as the bandwidth
# allows.
#
#   docker build -t celegans-sim .
#   docker run --rm -p 8080:8080 celegans-sim
#
# The build stage regenerates the model and the .wasm from source rather than trusting
# whatever happens to be checked in, and fails the build if the port stops matching the
# Python. A container that quietly ships a diverged model would be worse than no container.

# ---- stage 1: build the model and compile the runtime, then prove they agree ----------
FROM python:3.11-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY requirements.txt* ./
RUN pip install --no-cache-dir numpy
COPY worm/ worm/
COPY tools/ tools/
COPY data/ data/
COPY wasm/ wasm/
COPY web/ web/
ENV PYTHONPATH=/src
RUN python tools/export_model.py \
 && cd wasm && npm ci --no-audit --no-fund && npx asc assembly/index.ts --target release
RUN python tools/conform.py > web/conform.json \
 && node wasm/conform.mjs                      # the build fails here if the port drifted

# ---- stage 2: nothing but the files ---------------------------------------------------
FROM nginx:alpine
COPY --from=build /src/web/ /usr/share/nginx/html/
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
