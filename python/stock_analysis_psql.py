import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

# Database connection config
DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432")
}
DB_URL = f"postgresql://{DB_PARAMS['user']}:{DB_PARAMS['password']}@{DB_PARAMS['host']}:{DB_PARAMS['port']}/{DB_PARAMS['dbname']}"
ENGINE = create_engine(DB_URL)

def get_indonesia_stocks_data(engine=ENGINE):
    """
    Get Indonesian stock data from PostgreSQL database and apply a Buffett-style filter.
    Returns the top 10 stocks based on the 'buffett_score'.
    """
    print("Fetching Indonesian stock data from PostgreSQL...")
    
    # Query to get the latest financial data for each stock
    query = """
    WITH latest_fs AS (
        SELECT 
            code, 
            MAX(fs_date) as latest_date
        FROM 
            financial_ratios
        GROUP BY 
            code
    )
    SELECT 
        sf.sector, sf.sub_sector, sf.industry, sf.sub_industry, sf.code, sf.stock_name, sf.sharia, sf.fs_date, sf.fiscal_year_end, sf.assets, sf.liabilities, sf.equity, sf.sales, sf.ebt, sf.profit_period, sf.profit_attr_owner, sf.eps, sf.book_value, sf.per, sf.price_bv, sf.de_ratio, sf.roa, sf.roe, sf.npm
    FROM 
        financial_ratios sf
    JOIN 
        latest_fs lf ON sf.code = lf.code AND sf.fs_date = lf.latest_date
    ORDER BY 
        sf.sector, sf.sub_sector, sf.code
    """
    
    try:
        df = pd.read_sql(query, engine)
        
        # Ensure we only have the latest record for each stock (safeguard)
        df = df.sort_values(['code', 'fs_date'], ascending=[True, False])
        df = df.drop_duplicates(subset=['code'], keep='first')
        
        # Make sure numeric columns are properly typed
        numeric_columns = ['assets', 'liabilities', 'equity', 'sales', 'ebt', 
                          'profit_period', 'profit_attr_owner', 'eps', 'book_value', 
                          'per', 'price_bv', 'de_ratio', 'roa', 'roe', 'npm']
        
        df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce')

        # Buffett-style filtering (ROE >= 15%, Debt-to-Equity < 1, positive PER and PBV)
        df = df[
            (df['roe'] >= 15) &
            (df['de_ratio'] < 1) &
            (df['per'] > 0) &
            (df['price_bv'] > 0)
        ]

        # Calculate valuation score (lower is better)
        df['buffett_score'] = df['per'].rank() + df['price_bv'].rank()
        df = df.sort_values(by='buffett_score')
            
        # Limit to top 10
        top_buffett_stocks = df.head(10).reset_index(drop=True)

        return top_buffett_stocks
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame()


def main_analysis():
    """
    Main function to identify potentially undervalued Indonesian stocks
    from PostgreSQL database.
    """
    print("=== Indonesian Stock Value Analysis Tool (PSQL) ===")
    print("Disclaimer: This is for educational purposes only.")
    print("Always consult with a qualified financial advisor before making investment decisions.\n")
    
    stocks_data = get_indonesia_stocks_data()
    
    if stocks_data.empty:
        print("No stock data found or no stocks passed the filtering criteria. Exiting.")
        return
    
    print("\nTop Buffett-style Stocks:")
    print(stocks_data[['code', 'stock_name', 'roe', 'de_ratio', 'per', 'price_bv', 'buffett_score']])
    
    return stocks_data


if __name__ == "__main__":
    main_analysis()
