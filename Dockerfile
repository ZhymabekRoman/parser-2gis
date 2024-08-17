FROM python:3.12.3

WORKDIR /code

RUN apt-get update && apt-get install ffmpeg libsm6 libxext6 wget -y
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
RUN apt-get install -y ./google-chrome-stable_current_amd64.deb
RUN apt-get upgrade -y

RUN useradd -m appuser && chown -R appuser /code
USER appuser

COPY ./ /code

RUN pip install .

CMD ["python", "-m", "parser_2gis"]