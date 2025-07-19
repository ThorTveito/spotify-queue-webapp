FROM python:3.12-slim
WORKDIR /spotify-queue-webapp
COPY static ./static
COPY templates ./templates
COPY backend ./backend
RUN pip install -r backend/requirements.txt
RUN apt-get -y update; apt-get -y install curl
EXPOSE 8080/tcp
ENV ENV_NAME=PROD
ENV PYTHONUNBUFFERED=1
CMD ["python", "backend/app.py"]
