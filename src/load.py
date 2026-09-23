import pandas as pd
from sqlalchemy import create_engine
from getpass import getpass

# Read the cleaned CSV
file_path = "data/cleaned/online_retail_cleaned.csv"
df = pd.read_csv(file_path)

# Ask for your MySQL password securely
password = getpass("Enter MySQL root password: ")

# Connect Python to MySQL
engine = create_engine(
    f"mysql+pymysql://root:{password}@localhost:3306/retail_sales_db"
)

# Load the dataframe into MySQL
df.to_sql(
    "retail_sales",
    con=engine,
    if_exists="replace",
    index=False
)

print("Data loaded successfully into MySQL!")
print(f"Rows loaded: {len(df)}")

