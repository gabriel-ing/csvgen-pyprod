from intersystems_pyprod import (
    InboundAdapter,
    BusinessService,
    BusinessProcess,
    BusinessOperation,
    IRISLog,
    Status,
    JsonSerialize,
    IRISProperty,
    IRISParameter,
    Column
)
import os
import iris
import pandas as pd
import csv
import datetime
import re

iris_package_name = "CsvgenPyprod"

def _clean(name):
    # Strip invalid chars and prefix with underscore if starts with digit or string is empty
    name = re.sub(r"[^a-zA-Z0-9]", "", name)
    if not name or name[0].isdigit():
        name = "_" + name
    return name

def sanitize_identifier(name):
    # Double-quote to allow reserved words as SQL identifiers
    return f'"{_clean(name)}"'

def sanitize_table_name(name):
    return sanitize_identifier(name.replace(".csv", ""))

def raw_table_name(name):
    # Unquoted form for INFORMATION_SCHEMA lookups
    return _clean(name.replace(".csv", ""))

# Messages are the data structures passed between production components.
# JsonSerialize means they are serialized as JSON when stored in the message queue.

class FileMessage(JsonSerialize):
    file_path:str = Column()
    headers:list = Column()
    schema:str = Column()

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


# The InboundAdapter polls for new files and passes them to the BusinessService.
# IRISProperty values are configurable from the production UI at runtime.
class CSVInboundAdapter(InboundAdapter):
    inbound_file_dir: str = IRISProperty(description="Directory to monitor for new CSV files", settings="Adapter Settings" )
    working_file_dir: str = IRISProperty(description="Directory where files in progress are stored ")

    def __init__(self, iris_host_object):
        super().__init__(iris_host_object)
        self.processed_files = {}

    def OnTask(self):
        # OnTask is called on a schedule by the production framework
        i = 0

        while True:
            files = self._list_csvs()

            if not files:
                return Status.OK()

            file_name = files[i]

            # Skip files which previously errored to avoid retrying indefinitely
            if file_name in self.processed_files:
                    if self.processed_files[file_name][:5] == "ERROR":
                        IRISLog.Info(f"Skipping previously failed file: {file_name}")
                        i += 1
                        if i >= len(files):
                            return Status.OK()
                        continue

            file_path = os.path.join(self.inbound_file_dir, file_name)
            IRISLog.Info(f"Found new file to process: {file_path}")
            try:
                if self.working_file_dir:
                    new_path = os.path.join(self.working_file_dir, file_name)
                    os.rename(file_path, new_path)
                    file_path = new_path

                # Hand off to the BusinessService for processing
                self.business_host_process_input(file_path)

                self.processed_files[file_name] = f"Processing {datetime.datetime.now()}"

                return Status.OK()

            except Exception as e:
                self.processed_files[file_name] = f"ERROR {datetime.datetime.now()}"
                IRISLog.Error(f"Failed to process file: {file_path}, error: {str(e)}")
                return Status.ERROR(f"Failed to process file {file_name}: {str(e)}")


    def _list_csvs(self):
        csvs =  [f for f in os.listdir(self.inbound_file_dir) if f.endswith(".csv")]
        return csvs


# BusinessService receives input from the adapter, builds a message, and forwards it into the production.
class FromCSV(BusinessService):
    ADAPTER:str = IRISParameter(value="CsvgenPyprod.CSVInboundAdapter", description="CSV Watcher inbound adapter")
    process_target:str = IRISProperty(description="Business process to send message to", settings="Target Settings")

    def on_process_input(self, file_path):
        # Sniff the CSV dialect to handle different delimiters, then read headers
        with open(file_path, newline="", encoding="utf-8-sig") as f:
            sample = f.read(4096)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample)
            headers = next(csv.reader(f, dialect))

        IRISLog.Info(f"Recieved {file_path} with headers {str(headers)}")
        file_message = FileMessage(file_path=file_path, headers=headers)

        # send_request_async dispatches the message without waiting for a response
        status = self.send_request_async(self.process_target, file_message)


# BusinessOperation that checks whether a matching table already exists in the database.
# Returns a DBCheckResponse indicating existence and whether the column headers match.
class ToCheckDB(BusinessOperation):

    message_map = {
        f"{iris_package_name}.FileMessage":"search_for_table"
    }

    def search_for_table(self, input):
        file_name = input.file_path.split("/")[-1]
        table_name = raw_table_name(file_name)

        stmt = iris.sql.prepare("""SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                           WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?""")
        rs = stmt.execute(table_name, input.schema)
        rows = [x[0] for x in rs]

        if not rows:
            return Status.OK(), DBCheckResponse(exists=0, schema=input.schema, headers_match=0)

        # Table exists — check that all CSV headers are present as columns in the table.
        # Uses subset check so extra columns in the table (e.g. id) don't cause a mismatch.
        stmt = iris.sql.prepare("""SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                           WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?
                           ORDER BY ORDINAL_POSITION""")
        rs = stmt.execute(table_name, input.schema)
        table_columns = [x[0] for x in rs]

        sanitized_headers = {_clean(h).upper() for h in input.headers if _clean(h) not in ("", "_")}
        normalized_columns = {c.upper() for c in table_columns}
        headers_match = 1 if sanitized_headers <= normalized_columns else 0

        return Status.OK(), DBCheckResponse(exists=1, schema=input.schema, headers_match=headers_match)


# BusinessOperation that creates or inserts into a table in the IRIS database.
class ToDB(BusinessOperation):
    message_map = {
        f"{iris_package_name}.DBCreateRequest":"create_table",
        f"{iris_package_name}.DBUpdateRequest":"add_to_table"
    }
    file_archive = IRISProperty(description="Directory to archive CSV Files", settings="")

    def create_table(self, input):
        # Sample 50 rows to infer column types without reading the full file
        df = pd.read_csv(input.file_path, nrows=50)

        type_map = {
            "int64": "BIGINT",
            "float64": "DOUBLE",
            "bool": "BIT",
            "datetime64[ns]": "TIMESTAMP",
            "object": "VARCHAR(32000)"
        }

        columns = []
        for col, dtype in df.dtypes.items():
            if _clean(col) in ("", "_"):
                continue
            iris_type = type_map.get(str(dtype), "VARCHAR(32000)")
            columns.append(f"{sanitize_identifier(col)} {iris_type}")

        table_name = sanitize_table_name(input.file_path.split("/")[-1])
        columns_sql = ", ".join(columns)

        stmt = iris.sql.prepare(f"CREATE TABLE {input.schema}.{table_name} (id INTEGER, {columns_sql})")
        stmt.execute()

        IRISLog.Info(f"Table {input.schema}.{table_name} created!")
        return Status.OK()


    def add_to_table(self, input):
        file_name = input.file_path.split("/")[-1]
        table_name = sanitize_table_name(file_name)

        # Read headers only to build the prepared statement before streaming chunks
        all_col_names = pd.read_csv(input.file_path, nrows=0).columns
        col_names = [c for c in all_col_names if _clean(c) not in ("", "_")]
        columns = ", ".join(sanitize_identifier(c) for c in col_names)
        placeholders = ", ".join(["?" for _ in col_names])

        stmt = iris.sql.prepare(f"INSERT INTO {input.schema}.{table_name} ({columns}) VALUES ({placeholders})")

        # Stream the file in chunks to avoid loading it all into memory.
        # Convert bool columns to int — the IRIS-Python bridge passes Python bools as opaque objects.
        for chunk in pd.read_csv(input.file_path, chunksize=100000, usecols=col_names):
            bool_cols = chunk.select_dtypes(include="bool").columns
            chunk[bool_cols] = chunk[bool_cols].astype(int)
            for row in chunk.itertuples(index=False):
                stmt.execute(*row)

        if self.file_archive:
            archive_path = self.file_archive + "/" + file_name + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            os.rename(input.file_path, archive_path)
        return Status.OK()


# BusinessProcess that routes incoming file messages to the correct database operation.
# Acts as the orchestrator — decides whether to create a new table or insert into an existing one.
class Router(BusinessProcess):
    db_check_target = IRISProperty(description="Operation to check the database", settings="Target Settings")
    to_db_target = IRISProperty(description="Operation to add to the database", settings="Target Settings")

    default_schema = IRISProperty(description="Default schema to save files to", settings="TargetSettings")

    def on_request(self, input):

        # Check if a matching table already exists in the target schema
        check_request = FileMessage(file_path=input.file_path, headers=input.headers, schema=self.default_schema.replace(".", "_"))
        status, check_response = self.send_request_sync(self.db_check_target, check_request)

        schema = check_response.schema if check_response.exists and check_response.headers_match else self.default_schema
        schema = schema.replace(".", "_")

        if not check_response.exists:
            # No matching table — create one using the CSV structure
            create_request = DBCreateRequest(file_path=input.file_path, schema=schema)
            status = self.send_request_sync(self.to_db_target, create_request)

        elif not check_response.headers_match:
            IRISLog.Error(f"Headers do not match for file {input.file_path}, skipping.")
            return Status.ERROR(f"Headers do not match for {input.file_path}")

        # Insert the CSV data into the table
        update_request = DBUpdateRequest(file_path=input.file_path, schema=schema)
        status = self.send_request_async(self.to_db_target, update_request, response_required=0)

        return Status.OK()

    def on_response(self, a, b, c,d,e):
        return Status.OK()