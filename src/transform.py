import pandas as pd

# 1. Read the raw dataset
file_path = "data/raw/Online Retail.xlsx"
df = pd.read_excel(file_path)

print("Original dataset shape:")
print(df.shape)


# 2. Make a copy so we do not modify the raw data
cleaned_df = df.copy()


# 3. Remove rows missing important information
cleaned_df = cleaned_df.dropna(subset=["Description", "CustomerID"])


# 4. Remove duplicate rows
cleaned_df = cleaned_df.drop_duplicates()


# 5. Remove cancelled transactions
cleaned_df = cleaned_df[
    ~cleaned_df["InvoiceNo"].astype(str).str.startswith("C")
]


# 6. Remove invalid quantities and prices
cleaned_df = cleaned_df[
    (cleaned_df["Quantity"] > 0) &
    (cleaned_df["UnitPrice"] > 0)
]


# 7. Convert CustomerID from decimal-looking numbers to integers
cleaned_df["CustomerID"] = cleaned_df["CustomerID"].astype(int)


# 8. Create total revenue for each transaction line
cleaned_df["TotalPrice"] = (
    cleaned_df["Quantity"] * cleaned_df["UnitPrice"]
)


# 9. Save cleaned dataset
output_path = "data/cleaned/online_retail_cleaned.csv"

cleaned_df.to_csv(output_path, index=False)


# 10. Check our results
print("\nCleaned dataset shape:")
print(cleaned_df.shape)

print("\nMissing values after cleaning:")
print(cleaned_df.isnull().sum())

print("\nFirst 5 cleaned rows:")
print(cleaned_df.head())
