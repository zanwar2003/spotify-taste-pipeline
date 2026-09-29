FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV AGENT_HOST=0.0.0.0
CMD ["python", "-m", "tastepipe.agent.api"]
