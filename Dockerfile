FROM python:alpine

RUN apk --no-cache add git && pip3 install paho-mqtt python-dateutil

COPY . /data/app 
RUN sed -i "s|/etc/enverproxy.conf|/data/app/enverproxy.conf|g" /data/app/enverproxy.py 

WORKDIR /data/app
VOLUME /data/app

EXPOSE 1898

CMD ["python3", "./enverproxy.py"]
