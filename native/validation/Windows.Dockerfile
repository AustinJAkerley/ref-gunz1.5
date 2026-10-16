FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates cmake ninja-build g++-mingw-w64-x86-64-posix \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /source
ENTRYPOINT ["cmake"]