# Basic Template to get started with PyProd

Dockerfile installs pyprod with pip, correctly sets the required environmental variables. 

The ./src directory is mounted to /home/irisowner/dev meaning the files, including production.py is available here. 

The Merge.cpf file creates a new namespace ENSEMBLE which is the one used by pyprod (set by the environmental variable IRISNAMESPACE). 


