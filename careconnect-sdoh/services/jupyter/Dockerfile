FROM quay.io/jupyter/scipy-notebook:latest

USER root
RUN pip install --no-cache-dir \
    intersystems-irispython>=3.9.0 \
    httpx>=0.27 \
    plotly>=5.0

COPY notebooks/ /home/jovyan/work/

USER jovyan
EXPOSE 8888
