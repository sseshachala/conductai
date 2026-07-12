FROM python:3.11-slim

RUN pip install --quiet conduct-cli agent-booster

# Fake git identity so conduct-cli doesn't complain
RUN git config --global user.email "dev@conductai.ai" && \
    git config --global user.name "Dev Machine"

WORKDIR /workspace

CMD ["bash"]
