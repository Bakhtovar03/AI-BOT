# Используем компактный образ Python 3.13
FROM python:3.13-slim

# Устанавливаем системные зависимости для сборки Python-библиотек
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем весь проект в контейнер
COPY . .

# Устанавливаем виртуальное окружение и активируем его
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Устанавливаем зависимости Python
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Точка входа: запуск основного скрипта
CMD ["python", "main.py"]
