import yfinance as yf
import pandas as pd
import time
import concurrent.futures
from tqdm import tqdm
import os
import threading

def get_idx_tickers():
    """
    Get a list of sample Indonesian stock tickers for yfinance.
    Indonesian stocks typically have .JK suffix on Yahoo Finance.
    """
    idx_tickers = [
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK",
        "UNVR.JK", "HMSP.JK", "BBNI.JK", "ICBP.JK", "KLBF.JK",
        # Add more tickers as needed
    ]
    return idx_tickers

class RateLimiter:
    def __init__(self, calls, period):
        self.calls = calls
        self.period = period
        self.timestamps = []
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            # Remove timestamps older than the period
            self.timestamps = [t for t in self.timestamps if now - t < self.period]
            if len(self.timestamps) >= self.calls:
                # Need to wait until the oldest call expires
                sleep_time = self.period - (now - self.timestamps[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                # Update timestamps after sleeping
                now = time.time()
                self.timestamps = [t for t in self.timestamps if now - t < self.period]
            self.timestamps.append(now)

# Create rate limiter: e.g., 5 calls per second max to avoid being overly aggressive
rate_limiter = RateLimiter(calls=5, period=1.0)

def get_financial_ratios(ticker):
    """Get key financial ratios for a given yfinance ticker."""
    rate_limiter.wait()
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Extract key financial ratios
        ratios = {
            'Symbol': ticker,
            'Name': info.get('longName', ''),
            'Sector': info.get('sector', ''),
            'Industry': info.get('industry', ''),
            
            # Valuation Ratios
            'Market Cap': info.get('marketCap', None),
            'P/E Ratio': info.get('trailingPE', None),
            'Forward P/E': info.get('forwardPE', None),
            'PEG Ratio': info.get('pegRatio', None),
            'Price/Sales': info.get('priceToSalesTrailing12Months', None),
            'Price/Book': info.get('priceToBook', None),
            'Enterprise Value/EBITDA': info.get('enterpriseToEbitda', None),
            'Enterprise Value/Revenue': info.get('enterpriseToRevenue', None),
            
            # Profitability Ratios
            'Profit Margin': info.get('profitMargins', None),
            'Operating Margin': info.get('operatingMargins', None),
            'Return on Assets': info.get('returnOnAssets', None),
            'Return on Equity': info.get('returnOnEquity', None),
            
            # Dividend Ratios
            'Dividend Yield': info.get('dividendYield', None),
            'Dividend Rate': info.get('dividendRate', None),
            'Payout Ratio': info.get('payoutRatio', None),
            
            # Financial Health
            'Current Ratio': info.get('currentRatio', None),
            'Quick Ratio': info.get('quickRatio', None),
            'Debt to Equity': info.get('debtToEquity', None),
            
            # Growth Metrics
            'Earnings Growth': info.get('earningsGrowth', None),
            'Revenue Growth': info.get('revenueGrowth', None),
        }
        
        return ratios
    
    except Exception as e:
        return {'Symbol': ticker, 'Error': str(e)}

def fetch_and_save_financial_ratios(output_file="indonesia_stock_financial_ratios.csv"):
    """Fetches financial ratios for IDX tickers and saves them to a CSV."""
    idx_tickers = get_idx_tickers()
    print(f"Found {len(idx_tickers)} Indonesian stocks to analyze (yfinance)")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # We need to maintain order of inputs. Use submit, keep futures in dict
        future_to_ticker = {executor.submit(get_financial_ratios, ticker): ticker for ticker in idx_tickers}
        # to process in order and update tqdm nicely, we can't easily wait as_completed AND keep exact list order trivially without sorting results later.
        # But wait, we just want to save it ordered? We can create a list and fill it at correct indices.
        results_map = {}
        for future in tqdm(concurrent.futures.as_completed(future_to_ticker), total=len(idx_tickers), desc="Fetching financial ratios"):
            ticker = future_to_ticker[future]
            try:
                ratios = future.result()
                results_map[ticker] = ratios
            except Exception as e:
                results_map[ticker] = {'Symbol': ticker, 'Error': str(e)}

    # Restore order
    results = [results_map[ticker] for ticker in idx_tickers]
    
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False)
    print(f"Financial ratios saved to {output_file}")
    
    return df

def get_stock_holders(ticker):
    """Get major, institutional, and mutual fund holders for a given ticker."""
    rate_limiter.wait()
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        major_holders_df = pd.DataFrame()
        try:
            major_holders = stock.major_holders
            if major_holders is not None and not major_holders.empty:
                major_holders_df = major_holders.rename(columns={0: 'Value', 1: 'Description'})
        except Exception:
            pass
        
        institutional_holders_df = pd.DataFrame()
        try:
            institutional_holders = stock.institutional_holders
            if institutional_holders is not None and not institutional_holders.empty:
                institutional_holders_df = institutional_holders
        except Exception:
            pass
        
        mutualfund_holders_df = pd.DataFrame()
        try:
            mutualfund_holders = stock.mutualfund_holders
            if mutualfund_holders is not None and not mutualfund_holders.empty:
                mutualfund_holders_df = mutualfund_holders
        except Exception:
            pass
            
        return {
            'symbol': ticker,
            'name': info.get('longName', ''),
            'major_holders': major_holders_df,
            'institutional_holders': institutional_holders_df,
            'mutualfund_holders': mutualfund_holders_df
        }
        
    except Exception as e:
        return {'symbol': ticker, 'error': str(e)}

def get_stock_insiders(ticker):
    """Get insider trading data and roster for a given ticker."""
    rate_limiter.wait()
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        insider_trades_df = pd.DataFrame()
        try:
            insider_trades = stock.insider_transactions
            if insider_trades is not None and not insider_trades.empty:
                insider_trades_df = insider_trades
        except Exception:
            pass

        insider_roster_df = pd.DataFrame()
        try:
            insider_roster = stock.insider_roster
            if insider_roster is not None and not insider_roster.empty:
                insider_roster_df = insider_roster
        except Exception:
            pass
            
        return {
            'symbol': ticker,
            'name': info.get('longName', ''),
            'insider_trades': insider_trades_df,
            'insider_roster': insider_roster_df
        }
        
    except Exception as e:
        return {'symbol': ticker, 'error': str(e)}

def save_holders_data(holders_data, output_dir="."):
    """Save holders data to CSV files."""
    all_major_holders = []
    all_institutional_holders = []
    all_mutualfund_holders = []
    
    for data in holders_data:
        symbol = data['symbol']
        name = data.get('name', '')
        
        if 'major_holders' in data and not data['major_holders'].empty:
            df = data['major_holders'].copy()
            df['Symbol'] = symbol
            df['Name'] = name
            all_major_holders.append(df)
        
        if 'institutional_holders' in data and not data['institutional_holders'].empty:
            df = data['institutional_holders'].copy()
            df['Symbol'] = symbol
            df['Name'] = name
            all_institutional_holders.append(df)
        
        if 'mutualfund_holders' in data and not data['mutualfund_holders'].empty:
            df = data['mutualfund_holders'].copy()
            df['Symbol'] = symbol
            df['Name'] = name
            all_mutualfund_holders.append(df)
    
    # Save to CSV files
    if all_major_holders:
        major_holders_df = pd.concat(all_major_holders, ignore_index=True)
        major_holders_df.to_csv(os.path.join(output_dir, "indonesia_major_holders.csv"), index=False)
        print(f"Major holders data saved to {os.path.join(output_dir, 'indonesia_major_holders.csv')}")
    
    if all_institutional_holders:
        inst_holders_df = pd.concat(all_institutional_holders, ignore_index=True)
        inst_holders_df.to_csv(os.path.join(output_dir, "indonesia_institutional_holders.csv"), index=False)
        print(f"Institutional holders data saved to {os.path.join(output_dir, 'indonesia_institutional_holders.csv')}")
    
    if all_mutualfund_holders:
        fund_holders_df = pd.concat(all_mutualfund_holders, ignore_index=True)
        fund_holders_df.to_csv(os.path.join(output_dir, "indonesia_mutualfund_holders.csv"), index=False)
        print(f"Mutual fund holders data saved to {os.path.join(output_dir, 'indonesia_mutualfund_holders.csv')}")

def save_insiders_data(insiders_data, output_dir="."):
    """Save insiders data to CSV files."""
    all_insider_trades = []
    all_insider_roster = []
    
    for data in insiders_data:
        symbol = data['symbol']
        name = data.get('name', '')
        
        if 'insider_trades' in data and not data['insider_trades'].empty:
            df = data['insider_trades'].copy()
            df['Symbol'] = symbol
            df['Name'] = name
            all_insider_trades.append(df)
        
        if 'insider_roster' in data and not data['insider_roster'].empty:
            df = data['insider_roster'].copy()
            df['Symbol'] = symbol
            df['Name'] = name
            all_insider_roster.append(df)
    
    if all_insider_trades:
        insider_trades_df = pd.concat(all_insider_trades, ignore_index=True)
        insider_trades_df.to_csv(os.path.join(output_dir, "indonesia_insider_trades.csv"), index=False)
        print(f"Insider trades data saved to {os.path.join(output_dir, 'indonesia_insider_trades.csv')}")
    
    if all_insider_roster:
        insider_roster_df = pd.concat(all_insider_roster, ignore_index=True)
        insider_roster_df.to_csv(os.path.join(output_dir, "indonesia_insider_roster.csv"), index=False)
        print(f"Insider roster data saved to {os.path.join(output_dir, 'indonesia_insider_roster.csv')}")

def _fetch_holder_insider(ticker):
    holder_info = get_stock_holders(ticker)
    insider_info = get_stock_insiders(ticker)
    return holder_info, insider_info

def main_holders_insiders():
    """Main function to fetch and save holders and insiders data."""
    idx_tickers = get_idx_tickers()
    
    holders_data = []
    insiders_data = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ticker = {executor.submit(_fetch_holder_insider, ticker): ticker for ticker in idx_tickers}
        
        results_map = {}
        for future in tqdm(concurrent.futures.as_completed(future_to_ticker), total=len(idx_tickers), desc="Fetching holders and insiders data"):
            ticker = future_to_ticker[future]
            try:
                holder_info, insider_info = future.result()
                results_map[ticker] = (holder_info, insider_info)
            except Exception as e:
                # Fallback on errors
                holder_info = {'symbol': ticker, 'error': str(e)}
                insider_info = {'symbol': ticker, 'error': str(e)}
                results_map[ticker] = (holder_info, insider_info)
        
    for ticker in idx_tickers:
        holder_info, insider_info = results_map[ticker]
        holders_data.append(holder_info)
        insiders_data.append(insider_info)
    
    save_holders_data(holders_data)
    save_insiders_data(insiders_data)
    
    print("Holders and insiders data collection complete!")

if __name__ == "__main__":
    print("Starting data fetching from yfinance...")
    
    # Run both ratio fetching and holders/insiders fetching
    fetch_and_save_financial_ratios()
    print("-" * 40)
    main_holders_insiders()
