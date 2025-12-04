FROM coady/pylucene:9.12

WORKDIR /app
COPY . /app

ENV PYSPARK_PYTHON=python \
    PYSPARK_DRIVER_PYTHON=python \
    SPARK_LOCAL_IP=127.0.0.1

RUN pip install --no-cache-dir pyspark requests selenium tiktoken

CMD ["python", "cli.py"]
