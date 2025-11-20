FROM coady/pylucene:9.12

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir pyspark

CMD ["python", "main.py"]
