ARG CUDA_VERSION=12.8.1
ARG UBUNTU_VERSION=24.04
ARG CUDA_DEVEL_DIGEST=sha256:520292dbb4f755fd360766059e62956e9379485d9e073bbd2f6e3c20c270ed66
ARG CUDA_RUNTIME_DIGEST=sha256:ebef3c171eeef0298e4eb2e4be843105edf3b8b0ac45e0b43acee358e8046867

FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION}@${CUDA_DEVEL_DIGEST} AS build

ARG LLAMA_CPP_COMMIT=3cb7ffb1a1f612d5e4a46244ae5a3c77ad934a70

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
        ninja-build \
    && rm -rf /var/lib/apt/lists/*

RUN git init /src/llama.cpp \
    && git -C /src/llama.cpp remote add origin https://github.com/ggml-org/llama.cpp.git \
    && git -C /src/llama.cpp fetch --depth 1 origin "${LLAMA_CPP_COMMIT}" \
    && git -C /src/llama.cpp checkout --detach FETCH_HEAD \
    && test "$(git -C /src/llama.cpp rev-parse HEAD)" = "${LLAMA_CPP_COMMIT}" \
    && cmake -S /src/llama.cpp -B /src/llama.cpp/build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_CUDA=ON \
        -DGGML_CUDA_FA_ALL_QUANTS=ON \
        -DCMAKE_CUDA_ARCHITECTURES=86 \
        -DLLAMA_BUILD_SERVER=ON \
        -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=ON \
        -DLLAMA_CURL=OFF \
        -DBUILD_SHARED_LIBS=OFF \
    && cmake --build /src/llama.cpp/build --target llama-server llama-bench llama-cli -j "$(nproc)" \
    && /src/llama.cpp/build/bin/llama-server --version

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION}@${CUDA_RUNTIME_DIGEST}

ARG LLAMA_CPP_COMMIT=3cb7ffb1a1f612d5e4a46244ae5a3c77ad934a70
LABEL org.opencontainers.image.title="qwen-gpu-worker" \
      org.opencontainers.image.description="Provider-neutral llama.cpp server for a disposable Qwen coding worker" \
      org.opencontainers.image.source="local prototype" \
      org.opencontainers.image.version="${LLAMA_CPP_COMMIT}"

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gosu \
        jq \
        libgomp1 \
        python3 \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /bin/bash worker \
    && mkdir -p /models /results \
    && chown worker:worker /models /results

COPY --from=build /src/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server
COPY --from=build /src/llama.cpp/build/bin/llama-bench /usr/local/bin/llama-bench
COPY --from=build /src/llama.cpp/build/bin/llama-cli /usr/local/bin/llama-cli
COPY --chown=worker:worker config /app/config
COPY --chown=worker:worker scripts /app/scripts
COPY --chown=worker:worker prompts /app/prompts

ENV PROFILE=baseline \
    MODEL_DIR=/models \
    RESULTS_DIR=/results \
    LLAMA_HOST=0.0.0.0 \
    LLAMA_PORT=8000 \
    LLAMA_CPP_RELEASE=b10453 \
    LLAMA_CPP_COMMIT=${LLAMA_CPP_COMMIT}

WORKDIR /app
EXPOSE 8000
VOLUME ["/models", "/results"]
ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/entrypoint.sh"]
