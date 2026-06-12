from intersystems_pyprod import (
    Production,
    ServiceItem, 
    OperationItem, 
    ProcessItem
)

iris_package_name = "CSVGen"

class CSVGenProduction(Production): 
    services = [
        ServiceItem("FromCSV", 
                    "CSVGen.FromCSV", 
                    adapter_settings={
                        "inbound_file_dir":"/home/irisowner/dev/IN",
                        "working_file_dir":"/home/irisowner/dev/WORKING" 
                    }, 
                    host_settings = {
                        "process_target": "Router"
                    })
        
    ]
    processes = [
        ProcessItem("Router", 
                    "CSVGen.Router",
                    host_settings = {
                        "db_check_target":"ToCheckDB",
                        "to_db_target":"ToDatabase",
                        "default_schema":"CSVGen.Tables"
                    } 
                    )
    ] 
    
    operations = [
        OperationItem("ToCheckDB", 
                      "CSVGen.ToCheckDB"),
        OperationItem("ToDB", 
                      "CSVGen.ToDB",
                       host_settings = {
                           "file_archive": "/home/irisowner/dev/OUT"
                       } )            
    ]