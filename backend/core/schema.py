SCHEMAS = {

    "Customer": [
        "CustomerID",
        "FirstName",
        "LastName",
        "Email"
    ],

    "Vehicle": [
        "VIN",
        "Year",
        "Make",
        "Model",
        "Price"
    ],

    "Lead": [
        "LeadID",
        "FirstName",
        "LastName",
        "Source"
    ],

    "FinanceContract": [
        "FinanceNumber",
        "CustomerID",
        "VIN",
        "LenderName"
    ],

    "Lender": [
        "Name"
    ],

    "ServiceRecord": [
        "ServiceNumber",
        "CustomerID",
        "VIN",
        "Description"
    ],

    "Employee": [
        "EmployeeID",
        "FirstName",
        "LastName",
        "Department"
    ]
}