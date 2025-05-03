import pandas as pd # for data manipulation
import numpy as np # for numerical operations
import os # to handle file paths
import shutil # to move files

def clean_rental_data(df):
    """
    Clean rental property dataset by formatting specific columns and handling data types.
    
    Parameters:
    df (DataFrame): Input DataFrame to clean
    Returns:
    DataFrame: Cleaned DataFrame
    """
    # Create a copy to avoid modifying the original
    df = df.copy()
    
    # Remove empty rows (where all values are null)
    df = df.dropna(how='all')
    
    # Clean monthly_rent column
    def clean_rent(rent):
        try:
            if pd.isna(rent):
                return np.nan # Handle NaN values
            
            # Convert to string first to handle any numeric inputs
            rent_str = str(rent)
            # Remove currency symbol, commas, and 'per month'
            cleaned = rent_str.replace('RM ', '').replace(' per month', '').replace(',', '')
            # Convert to float, return nan if fails
            return float(cleaned) if cleaned.strip() else np.nan
        except:
            return np.nan
    
    if 'monthly_rent' in df.columns:
        df['monthly_rent'] = df['monthly_rent'].apply(clean_rent)
    
    # Clean category_id column
    if 'category_id' in df.columns:
        df['category_id'] = df['category_id'].fillna('').astype(str).str.replace(', For rent', '')
    
    # Clean size column
    def clean_size(size):
        try:
            if pd.isna(size):
                return np.nan
            # Convert to string first to handle any numeric inputs
            size_str = str(size)
            # Remove 'sq.ft.' and commas
            cleaned = size_str.replace(' sq.ft.', '').replace(',', '')
            # Convert to float, return nan if fails
            return float(cleaned) if cleaned.strip() else np.nan
        except:
            return np.nan
    
    if 'size' in df.columns:
        df['size'] = df['size'].apply(clean_size)
    
    # Clean and convert publishedDatetime column
    if 'publishedDatetime' in df.columns:
        try:
            df['publishedDatetime'] = pd.to_datetime(df['publishedDatetime'], errors='coerce').dt.strftime('%m/%d/%Y')
            # Fill NaT values with a placeholder or empty string
            df['publishedDatetime'] = df['publishedDatetime'].fillna('')
        except:
            # If datetime conversion fails, keep the original values
            pass
    
    return df

def create_mapping_dict(mapping_df):
    """
    Create a dictionary from the mapping DataFrame, removing 'Sewa' prefix.
    """
    mapping_dict = {}
    for _, row in mapping_df.iterrows():
        mudah_type = row['Mudah Property Type']
        if pd.notna(mudah_type):
            if '\n' in str(mudah_type):
                types = mudah_type.split('\n')
                for t in types:
                    if t.strip():
                        std_type = row['Standardized Property Type']
                        if pd.notna(std_type) and str(std_type).startswith('Sewa '):
                            mapping_dict[t.strip()] = str(std_type)[5:]
            else:
                std_type = row['Standardized Property Type']
                if pd.notna(std_type) and str(std_type).startswith('Sewa '):
                    mapping_dict[str(mudah_type)] = str(std_type)[5:]
    return mapping_dict

def map_property_type(property_type, mapping_dict):
    """
    Map a property type to its standardized version.
    """
    if pd.isna(property_type):
        return 'Other'
    return mapping_dict.get(str(property_type).strip(), 'Other')

def process_rental_data(source_folder, csv_folder, final_folder, master_file, mapping_file):
    """
    Main function to process rental data: clean, combine, and map property types.
    """
    try:
        # Create folders if they don't exist
        os.makedirs(csv_folder, exist_ok=True)
        os.makedirs(final_folder, exist_ok=True)
        
        # Step 1: Clean and combine CSV files from the source folder
        combined_df = pd.DataFrame()
        for filename in os.listdir(source_folder):
            if filename.endswith('.csv'):
                csv_path = os.path.join(source_folder, filename)
                
                try:
                    # Read and clean each CSV file
                    df = pd.read_csv(csv_path)
                    cleaned_df = clean_rental_data(df)
                    
                    # Combine with existing data
                    combined_df = pd.concat([combined_df, cleaned_df], ignore_index=True) if not combined_df.empty else cleaned_df
                    
                    print(f"Processed: {filename}")
                except Exception as e:
                    print(f"Error processing {filename}: {str(e)}")
                    continue
        
        if combined_df.empty:
            print("No data was processed successfully.")
            return
        
        # Step 2: Merge with existing master file if it exists
        master_path = os.path.join(final_folder, master_file)
        if os.path.exists(master_path):
            master_df = pd.read_csv(master_path)
            common_columns = master_df.columns.intersection(combined_df.columns)
            combined_df = pd.concat([master_df, combined_df[common_columns]], ignore_index=True)
        
        # Remove duplicates
        combined_df.drop_duplicates(inplace=True)
        
        # Step 3: Apply property type mapping
        mapping_df = pd.read_csv(mapping_file)
        mapping_dict = create_mapping_dict(mapping_df)
        
        if 'property_type' in combined_df.columns:
            combined_df['CPI'] = combined_df['property_type'].apply(lambda x: map_property_type(x, mapping_dict))
        
        # Step 4: Save the final result
        combined_df.to_csv(master_path, index=False)
        
        # Step 5: Move processed files to csv folder
        for filename in os.listdir(source_folder):
            if filename.endswith('.csv'):
                source_path = os.path.join(source_folder, filename)
                dest_path = os.path.join(csv_folder, filename)
                shutil.move(source_path, dest_path)
        
        print("\nProcessing Summary:")
        print(f"Total records in master file: {len(combined_df)}")
        if 'property_type' in combined_df.columns:
            print(f"Number of unique properties: {combined_df['property_type'].nunique()}")
        if 'publishedDatetime' in combined_df.columns and not combined_df['publishedDatetime'].empty:
            valid_dates = combined_df['publishedDatetime'].dropna()
            if not valid_dates.empty:
                print(f"Date range: {valid_dates.min()} to {valid_dates.max()}")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    # Configuration
    source_folder = 'D:/3. Data Analysis Project/Mudah Website/Mudah Rental Properties/Scraped Data'
    csv_folder = 'D:/3. Data Analysis Project/Mudah Website/Mudah Rental Properties/Scraped Data/csv'
    final_folder = 'D:/3. Data Analysis Project/Mudah Website/Mudah Rental Properties'
    master_file = 'MasterFile.csv'
    mapping_file = 'D:/3. Data Analysis Project/Mudah Website/Mudah Rental Properties/Table.csv'
    
    # Run the processing
    process_rental_data(source_folder, csv_folder, final_folder, master_file, mapping_file)