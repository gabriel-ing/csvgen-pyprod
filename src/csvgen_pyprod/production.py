from intersystems_pyprod import (
    Production,
    ServiceItem,
    OperationItem,
    ProcessItem
)

iris_package_name = "CsvgenPyprod"

FILE_WATCHER_ROOT = "/home/irisowner/dev/Data"

class Prod(Production):
    services = [
        ServiceItem("FromCSV",
                    "CsvgenPyprod.FromCSV",
                    adapter_settings={
                        "inbound_file_dir":f"{FILE_WATCHER_ROOT}/IN",
                        "working_file_dir":f"{FILE_WATCHER_ROOT}/WORKING"
                    },
                    host_settings = {
                        "process_target": "Router"
                    })

    ]
    processes = [
        ProcessItem("Router",
                    "CsvgenPyprod.Router",
                    host_settings = {
                        "db_check_target":"ToCheckDB",
                        "to_db_target":"ToDB",
                        "default_schema":"CsvgenPyprod.Tables"
                    }
                    )
    ]

    operations = [
        OperationItem("ToCheckDB",
                      "CsvgenPyprod.ToCheckDB"),
        OperationItem("ToDB",
                      "CsvgenPyprod.ToDB",
                       host_settings = {
                           "file_archive": f"{FILE_WATCHER_ROOT}/OUT"
                       } )
    ]
