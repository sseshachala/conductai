FROM python:3.11-slim

RUN apt-get update -qq && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN pip install --quiet conduct-cli agent-booster

RUN git config --global user.email "dev@conductai.ai" && \
    git config --global user.name "Dev Machine"

WORKDIR /workspace

CMD ["bash"]
