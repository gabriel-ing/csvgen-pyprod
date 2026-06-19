# CsvgenPyprod production in PyProd

This project implements a `csvgen` interoperability production with InterSystems PyProd. It watches a directory for new CSV files (InboundAdapter + Business Service), passes them to a router (Business Process), which first sends a synchronous request to the `ToCheckDB` host (Business Operation) to check whether a table with the same name as the file already exists. The result is passed back to the router, which may then send a create-table request to `ToDB` (Business Operation), and finally sends a request to `ToDB` to insert the data.

This is a basic example of using PyProd to create productions in InterSystems, and was implemented as part of the InterSystems Developer Community **Idea to Application** program.

## Get started

Clone the repo:

```
git clone https://github.com/gabriel-ing/pyprod-csvgen.git
cd pyprod-csvgen
```

Start up the Docker container:

```
docker-compose up --build -d
```

The components and production files are loaded during the Docker build, so you just need to start the production. This can be done through the management portal at:

http://localhost:62773/csp/ensemble/EnsPortal.ProductionConfig.zen?$NAMESPACE=ENSEMBLE&PRODUCTION=CsvgenPyprod.Prod

Or with the `controls.py` file:

```
python3 controls.py start CsvgenPyprod.Prod
```

After this, you can test the production by placing any CSV file into the `./IN` directory. After a few seconds you should see it move to `WORKING`, then when complete, to `OUT`. Take a look at the production portal and messages viewer to see the message trace.

> [!WARNING]
> This interoperability production is meant as a demo application to show the use of PyProd. It is not designed for production usage.


## Manual Loading

The production is contained in two Python files, [components.py](./src/csvgen_pyprod/components.py) and [production.py](./src/csvgen_pyprod/production.py). The components file contains the definition of the business hosts (Services, Processes, Operations), the Inbound Adapter, and the message class. The production file contains the production definition. Because `CsvgenPyprod.Prod` is defined as a Production class, its settings should not be adjusted in the UI. You can alternatively define productions in the UI using the host components from the components file.

If you are doing this outside the docker-compose build in this repo, ensure PyProd is set up properly — [instructions below](#pyprod-setup).

To register the components and production in IRIS, open a shell in the container:

```bash
docker-compose exec -it iris bash
```

Then run:

```bash
intersystems_pyprod src/csvgen_pyprod/components.py
intersystems_pyprod src/csvgen_pyprod/production.py
```

## PyProd Setup

Set the following environment variables so Python can locate the IRIS libraries:

```bash
export IRISINSTALLDIR="/usr/irissys"
export LD_LIBRARY_PATH="$IRISINSTALLDIR/bin:$LD_LIBRARY_PATH"
export IRISUSERNAME="SuperUser"
export IRISPASSWORD="SYS"
export IRISNAMESPACE="ENSEMBLE"
export PYTHONPATH="$IRISINSTALLDIR/lib/python"
export PATH="/usr/irissys/lib/python/bin:$PATH"
```

Then install the PyProd package into the IRIS Python environment:

```bash
python3 -m pip install intersystems_pyprod --target /usr/irissys/lib/python
```
