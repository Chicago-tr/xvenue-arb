FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    openjdk-21-jre\
    build-essential \
    libpq-dev \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-arm64
ENV PATH=$PATH:$JAVA_HOME/bin

RUN curl -L -o /tmp/postgresql.jar https://jdbc.postgresql.org/download/postgresql-42.7.10.jar

RUN useradd -m -u 1000 -s /bin/bash sparkuser && \
    mkdir -p /app && \
    mv /tmp/postgresql.jar /app/postgresql-42.7.10.jar && \
    chown -R sparkuser:sparkuser /app
USER sparkuser


WORKDIR /app



COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY src/ ./src/


EXPOSE 8050

CMD ["echo", "Use docker-compose to start services"]
