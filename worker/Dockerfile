FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp

# Optional: headless Claude Code for llm_backend: "cli"
ARG INSTALL_CLAUDE_CLI=false
RUN if [ "$INSTALL_CLAUDE_CLI" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends nodejs npm \
      && npm install -g @anthropic-ai/claude-code \
      && rm -rf /var/lib/apt/lists/*; \
    fi

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin mailforge
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mailforge/ ./mailforge/
RUN mkdir -p /app/data /app/reports /app/config && chown -R mailforge /app/data /app/reports

USER mailforge
# Idle container; Ofelia runs `python -m mailforge.main` inside it on schedule.
CMD ["sleep", "infinity"]
