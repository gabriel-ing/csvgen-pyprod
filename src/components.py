from intersystems_pyprod import (
    InboundAdapter,
    BusinessService, 
    BusinessProcess, 
    BusinessOperation,
    IRISLog,
    Status, 
    PickleSerialize,
    JsonSerialize,
    IRISProperty,
    IRISParameter,
    Column
)
import os
import iris
import pandas as pd 
import csv
import copy
import datetime

iris_package_name = "CSVGen"

class FileMessage(PickleSerialize):
    file_path:str = Column()
    headers:list = Column()


class DBCheckResponse(JsonSerialize):
    exists:bool = Column()
    schema:str = Column()
    headers_match:bool = Column()

class DBCreateRequest(JsonSerialize):
    file_path:str = Column()
    schema:str = Column()

class DBUpdateRequest(JsonSerialize):
    file_path:str=Column()
    schema:str = Column()


class CSVInboundAdapter():
    inbound_file_dir: str = IRISProperty(description="Directory to monitor for new CSV files", settings="Adapter Settings" )
    working_file_dir: str = IRISProperty(description="Directory where files in progress are stored ")

    def __init__(self, iris_host_object):
        super().__init__(iris_host_object)
        self.processed_files = {}

    def OnTask(self):
        
        i = 0 

        # Loop in case files are skipped
        while True:
            
            # Get CSV files in directory
            files = self._list_csvs()
            
            # If no files are found, return OK and await next task execution 
            if not files:
                return Status.OK()
            
            # Process the first file
            file_name = files[i]
            
            # Skip files which previously errored
            if file_name in self.processed_files:
                    if self.processed_files[file_name][:5] == "ERROR":
                        IRISLog.Info(f"Skipping previously failed file: {file_name}")
                        i += 1
                        continue

            
            file_path = os.path.join(self.inbound_file_dir, file_name)
            IRISLog.Info(f"Found new file to process: {file_path}")
            try: 
                
                
                if self.working_file_dir:
                    new_path = os.path.join(self.working_file_dir, file_name)
                    # Move processed file to archive directory
                    os.rename(file_path, new_path)
                    file_path = new_path
                
                self.business_host_process_input(file_path)

                # Add the file to the processed files dictionary 
                self.processed_files[file_name] = f"Processing {datetime.datetime.now()}"

                return Status.OK()
        
            except Exception as e:

                self.processed_files[file_name] = f"ERROR {datetime.datetime.now()}"
                IRISLog.Error(f"Failed to process file: {file_path}, error: {str(e)}")
                return Status.ERROR(f"Failed to process file {file_name}: {str(e)}")


    def _list_csvs(self):
        """Helper method to list CSV files in the inbound_file_dir"""
        csvs =  [f for f in os.listdir(self.inbound_file_dir) if f.endswith(".csv")]
        return csvs
    

class FromCSV():
    ADAPTER = IRISParameter(value="CSVGen.CSVInboundAdapter", description="CSV Watcher inbound adapter")
    process_target = IRISProperty(description="Business process to send message to", settings="Target Settings")

    def on_process_input(self, file_path):
        
        
                        # Find the headers of the file
        with open(file_path, newline="", encoding="utf-8-sig") as f:
            sample = f.read(4096)
            f.seek(0)

            dialect = csv.Sniffer().sniff(sample)
            headers = next(csv.reader(f, dialect))

        IRISLog.Info(f"Recieved {file_path} with headers {str(headers)}")
        file_message = FileMessage(file_path=file_path, headers=headers)

        status = self.send_request_async(self.process_target, file_message)
        




class ToCheckDB(BusinessOperation):

    message_map = {
        f"{iris_package_name}.FileMessage":"search_for_table"
    }

    def search_for_table(self, input):
        file_name = input.file_path.split("/")[-1]

        ## See if table exists
        stmt = iris.sql.prepare("""SELECT TABLE_SCHEMA FROM INFORMATION_SCHEMA.TABLES
                           WHERE TABLE_NAME = ?""")
        rs = stmt.execute(file_name)
        rows = [x[0] for x in rs]

        if not rows:
            return Status.OK(), DBCheckResponse(exists=False, schema="", headers_match=False)

        table_schema = rows[0]

        
        ## Check if column headers match input headers
        stmt = iris.sql.prepare("""SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                           WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?
                           ORDER BY ORDINAL_POSITION""")
        rs = stmt.execute(file_name, table_schema)
        table_columns = [x[0] for x in rs]

        headers_match = set(input.headers) <= set(table_columns)

        return Status.OK(), DBCheckResponse(exists=True, schema=table_schema, headers_match=headers_match)



class ToDB(BusinessOperation):
    message_map = {
        f"{iris_package_name}.DBCreateRequest":"create_table",
        f"{iris_package_name}.DBUpdateRequest":"add_to_table"
    }
    file_archive = IRISProperty(description="Directory to archive CSV Files", settings="")

    def create_table(self, input):

        # Read a subset of the file to infer column types
        df = pd.read_csv(input.file_path, nrows=50)

        type_map = {
            "int64": "BIGINT",
            "float64": "DOUBLE",
            "bool": "BOOLEAN",
            "datetime64[ns]": "TIMESTAMP",
            "object": "VARCHAR(255)"
        }

        columns = []
        for col, dtype in df.dtypes.items():
            iris_type = type_map.get(str(dtype), "VARCHAR(255)")
            columns.append(f"{col} {iris_type}")

        table_name = input.file_path.split("/")[-1].replace(".csv", "")
        columns_sql = ", ".join(columns)

        stmt = iris.sql.prepare(f"CREATE TABLE {input.schema}.{table_name} (id BIGINT GENERATED ALWAYS AS IDENTITY, {columns_sql})")
        stmt.execute()

        return Status.OK()


    def add_to_table(self, input):
        file_name = input.file_path.split("/")[-1]
        table_name = file_name.replace(".csv", "")

        col_names = pd.read_csv(input.file_path, nrows=0).columns
        columns = ", ".join(col_names)
        placeholders = ", ".join(["?" for _ in col_names])

        stmt = iris.sql.prepare(f"INSERT INTO {input.schema}.{table_name} ({columns}) VALUES ({placeholders})")

        for chunk in pd.read_csv(input.file_path, chunksize=100000):
            for row in chunk.itertuples(index=False):
                stmt.execute(*row)

        if self.file_archive:
            archive_path = self.file_archive + "/" + file_name + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            os.rename(input.file_path, archive_path)
        return Status.OK()
        
        
    

class Router(BusinessProcess):
    db_check_target = IRISProperty(description="Operation to check the database", settings="Target Settings")
    to_db_target = IRISProperty(description="Operation to add to the database", settings="Target Settings")
    
    default_schema = IRISProperty(description="Default schema to save files to", settings="TargetSettings")

    def on_request(self, input):

        check_request = FileMessage(file_path=input.file_path, headers=input.headers)
        status, check_response = self.send_request_sync(self.check_target, check_request)

        schema = check_response.schema if check_response.exists and check_response.headers_match else self.default_schema

        if not check_response.exists:
            create_request = DBCreateRequest(file_path=input.file_path, schema=schema)
            status = self.send_request_sync(self.to_db_target, create_request)
        
        elif not check_response.headers_match and check_response.schema!=self.default_schema:
            create_request = DBCreateRequest(file_path=input.file_path, schema=schema)
            status = self.send_request_sync(self.to_db_target, create_request)

        elif not check_response.headers_match:
            IRISLog.Error(f"Headers do not match for file {input.file_path}, skipping.")
            return Status.ERROR(f"Headers do not match for {input.file_path}")

        update_request = DBUpdateRequest(file_path=input.file_path, schema=schema)
        status = self.send_request_async(self.to_db_target, update_request)

        return Status.OK()