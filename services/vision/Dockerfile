FROM python:3.11-slim AS simulation
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY dock_vision ./dock_vision
RUN pip install .
CMD ["python", "-m", "dock_vision"]

FROM simulation AS inference
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install '.[vision]'
