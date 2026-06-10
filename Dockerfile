ARG IMAGE=intersystems/iris-community:latest-em
FROM $IMAGE

ENV IRISINSTALLDIR "/usr/irissys"
ENV LD_LIBRARY_PATH "$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH"
ENV IRISUSERNAME "SuperUser"
ENV IRISPASSWORD "SYS"
ENV IRISNAMESPACE "ENSEMBLE"
ENV COMLIB "$IRISINSTALLDIR/bin"
ENV PYTHONPATH "$IRISINSTALLDIR/lib/python"
ENV PATH "/usr/irissys/lib/python/bin:/usr/irissys/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/irisowner/bin:/home/irisowner/.local/bin"



WORKDIR /home/irisowner/dev

# COPY src/pyprod /home/irisowner/dev/pyprod
# RUN chown -R irisowner:irisowner /home/irisowner/dev/pyprod


RUN python3 -m pip install --break-system-packages intersystems_pyprod --target /usr/irissys/lib/python


RUN --mount=type=bind,src=.,dst=. \
    iris start IRIS && \
    iris merge IRIS merge.cpf && \
	iris session IRIS < iris.script && \
    iris stop IRIS quietly

    