FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates python3 python3-requests git cmake ninja-build clang lld llvm \
    msitools cabextract wine64 wine32:i386 wine winbind \
    libgl1-mesa-dri libgl1-mesa-dri:i386 libgl1 libgl1:i386 libegl1 libegl1:i386 \
    libvulkan1 libvulkan1:i386 mesa-vulkan-drivers mesa-vulkan-drivers:i386 \
    xauth xvfb x11-utils fonts-liberation file pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 1000 --create-home builder || true
ENV WINEDEBUG=-all
WORKDIR /work
RUN apt-get update && apt-get install -y --no-install-recommends python3-pil python3-xlib xdotool \
    && rm -rf /var/lib/apt/lists/*