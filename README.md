# Appian Development Project

A structured Appian application development workspace with templates, conventions, and reusable components.

## Project Structure

```
/
├── .appian/
│   └── config.json              # Project config & naming conventions
├── expression-rules/            # Reusable Expression Rules (.sail)
│   ├── APP_validateEmail.sail
│   ├── APP_formatCurrency.sail
│   └── APP_getStatusLabel.sail
├── interfaces/                  # SAIL Interface definitions
│   ├── APP_taskListInterface.sail
│   └── APP_taskFormInterface.sail
├── process-models/              # Process Model designs & docs
│   └── APP_TaskApprovalFlow.md
├── constants/                   # Constants reference
│   └── APP_constants.sail
├── record-types/                # Record Type definitions & docs
│   └── APP_TaskRecord.md
├── web-apis/                    # Web API definitions
│   └── APP_tasksApi.sail
├── integrations/                # Integration objects
├── data-stores/                 # Data Store entity schemas
├── groups/                      # Security group definitions
├── reports/                     # Report configurations
└── scripts/                     # Automation scripts
    ├── appian_workflow.py       # Main: Export → Modify → Deploy
    ├── appian_client.py         # Appian REST API client
    ├── exporter.py              # Export & extract packages
    ├── modifier.py              # Apply YAML-driven code patches
    ├── deployer.py              # Package & deploy via Deployment API
    ├── config.py                # Configuration loader
    ├── patches.yaml.example     # Example patch definitions
    ├── .env.example             # Environment variable template
    └── requirements.txt         # Python dependencies
```

## Naming Conventions

| Object Type      | Pattern                        | Example                        |
|------------------|--------------------------------|--------------------------------|
| Expression Rule  | `rule!APP_<RuleName>`          | `rule!APP_validateEmail`       |
| Interface        | `rule!APP_<Name>Interface`     | `rule!APP_taskListInterface`   |
| Constant         | `cons!APP_<CONSTANT_NAME>`     | `cons!APP_STATUS_APPROVED`     |
| Record Type      | `recordType!APP_<Name>Record`  | `recordType!APP_TaskRecord`    |
| Process Model    | `APP - <Process Model Name>`   | `APP - Task Approval Flow`     |
| Web API Endpoint | `/api/APP/<endpointName>`      | `/api/APP/tasks`               |
| Data Store       | `APP_DataStore`                | —                              |
| Group            | `APP - <Role Name>`            | `APP - Administrators`         |

## Automated Deployment Script

### Setup
```bash
cd scripts
pip install -r requirements.txt
cp .env.example .env
cp patches.yaml.example patches.yaml
```

### Usage
```bash
python appian_workflow.py --list-apps
python appian_workflow.py --app-uuid <UUID> --export-only
python appian_workflow.py --app-uuid <UUID> --patches patches.yaml
python appian_workflow.py --deploy-zip workspace/deploy_package.zip
```
