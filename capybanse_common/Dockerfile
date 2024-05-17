FROM python:3.12-slim-bookworm as capybanse_common
WORKDIR /app

# Установка Poetry без создания виртуального окружения
RUN pip install --no-cache-dir poetry
RUN poetry config virtualenvs.create false

# install current package
COPY pyproject.toml /app/
COPY . /app/
RUN pip install .
