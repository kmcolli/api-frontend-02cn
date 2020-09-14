FROM ubuntu:18.04
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
RUN apt-get update && apt-get install -y apt-transport-https python3.8 python3-pip socat
COPY . .
COPY requirements.txt .
RUN pip3 install -r requirements.txt
ENV FLASK_APP=api-frontend-02cn.py
EXPOSE 8000
ENTRYPOINT [ "python3" ]

CMD [ "app/api-frontend-02cn.py" ]