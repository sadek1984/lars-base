import pandas as pd
import numpy as np
from datetime import datetime

def extract_latest_adi_values(pesticide_list, file_path):
    """
    Extract the latest ADI values for a list of pesticides from OpenFoodTox database.
    
    Parameters:
    -----------
    pesticide_list : list
        List of pesticide names to search for
    file_path : str
        Path to the 'Reference_values_2023.xlsx' file
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame with columns: 'Pesticide', 'ADI_Value', 'ADI_Unit', 'Year', 'Author', 'OutputID'
    """
    
    # Read the Excel file
    try:
        # Try to read with sheet name
        df = pd.read_excel(file_path, sheet_name='REFERENCE_VALUES')
    except:
        # If sheet name not found, read first sheet
        df = pd.read_excel(file_path)
    
    # Standardize pesticide names in the list (lowercase for matching)
    pesticide_list_lower = [p.strip().lower() for p in pesticide_list]
    
    # Filter for ADI values for Consumers
    # Note: OpenFoodTox uses "ADI (Acceptable Daily Intake)" not just "ADI"
    adi_mask = df['Assessment'].astype(str).str.contains('ADI', case=False, na=False)
    consumer_mask = df['Population'].astype(str).str.contains('Consumer', case=False, na=False)
    
    adi_df = df[adi_mask & consumer_mask].copy()
    
    # Create a lowercase version of Substance column for matching
    adi_df['Substance_lower'] = adi_df['Substance'].astype(str).str.lower()
    
    # Initialize results list
    results = []
    
    print(f"Processing {len(pesticide_list)} pesticides...")
    print("-" * 80)
    
    # For each pesticide in the list, find all ADI entries and select the latest
    for i, pesticide in enumerate(pesticide_list):
        pesticide_lower = pesticide.lower()
        
        # Find matches - try exact match first, then partial match
        exact_matches = adi_df[adi_df['Substance_lower'] == pesticide_lower]
        
        if len(exact_matches) == 0:
            # Try partial match (substring)
            partial_matches = adi_df[adi_df['Substance_lower'].str.contains(pesticide_lower, na=False)]
            matches = partial_matches
        else:
            matches = exact_matches
        
        if len(matches) > 0:
            # Convert Year to numeric, handling any non-numeric values
            matches = matches.copy()
            matches['Year_numeric'] = pd.to_numeric(matches['Year'], errors='coerce')
            
            # Drop rows with NaN years
            matches = matches.dropna(subset=['Year_numeric'])
            
            if len(matches) > 0:
                # Get the entry with the latest year
                latest_idx = matches['Year_numeric'].idxmax()
                latest_entry = matches.loc[latest_idx]
                
                result = {
                    'Pesticide': pesticide,
                    'Matched_Name': latest_entry['Substance'],
                    'ADI_Value': latest_entry['value'],
                    'ADI_Unit': latest_entry['unit'],
                    'Year': int(latest_entry['Year_numeric']),
                    'Author': latest_entry['Author'],
                    'OutputID': latest_entry['OutputID'],
                    'Match_Type': 'Exact' if len(exact_matches) > 0 else 'Partial',
                    'Num_Entries': len(matches)
                }
                
                # Print progress for this pesticide
                print(f"{i+1:3d}. {pesticide:25s} → ADI: {latest_entry['value']} {latest_entry['unit']} (Year: {int(latest_entry['Year_numeric'])}, {len(matches)} entries)")
                
                results.append(result)
            else:
                # No valid year entries
                print(f"{i+1:3d}. {pesticide:25s} → NO ADI FOUND (no valid year data)")
                results.append({
                    'Pesticide': pesticide,
                    'Matched_Name': None,
                    'ADI_Value': None,
                    'ADI_Unit': None,
                    'Year': None,
                    'Author': None,
                    'OutputID': None,
                    'Match_Type': 'No match',
                    'Num_Entries': 0
                })
        else:
            # No matches found at all
            print(f"{i+1:3d}. {pesticide:25s} → NO ADI FOUND (no entries in database)")
            results.append({
                'Pesticide': pesticide,
                'Matched_Name': None,
                'ADI_Value': None,
                'ADI_Unit': None,
                'Year': None,
                'Author': None,
                'OutputID': None,
                'Match_Type': 'No match',
                'Num_Entries': 0
            })
    
    # Convert results to DataFrame
    results_df = pd.DataFrame(results)
    
    # Summary statistics
    print("-" * 80)
    found_count = results_df['ADI_Value'].notna().sum()
    print(f"\nSUMMARY:")
    print(f"Total pesticides processed: {len(pesticide_list)}")
    print(f"Pesticides with ADI found: {found_count}")
    print(f"Pesticides without ADI: {len(pesticide_list) - found_count}")
    
    return results_df

def export_results(results_df, output_format='excel'):
    """
    Export the results to file.
    
    Parameters:
    -----------
    results_df : pandas.DataFrame
        Results DataFrame from extract_latest_adi_values
    output_format : str
        'excel' or 'csv'
    """
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if output_format.lower() == 'excel':
        filename = f"pesticide_adi_results_{timestamp}.xlsx"
        results_df.to_excel(filename, index=False)
        print(f"\nResults exported to: {filename}")
        
        # Also create a simplified version with just key columns
        simplified_cols = ['Pesticide', 'ADI_Value', 'ADI_Unit', 'Year', 'Author']
        simplified_df = results_df[simplified_cols].copy()
        simplified_filename = f"pesticide_adi_simple_{timestamp}.xlsx"
        simplified_df.to_excel(simplified_filename, index=False)
        print(f"Simplified results exported to: {simplified_filename}")
        
    elif output_format.lower() == 'csv':
        filename = f"pesticide_adi_results_{timestamp}.csv"
        results_df.to_csv(filename, index=False)
        print(f"\nResults exported to: {filename}")
    
    return filename

def create_adi_lookup_function(results_df):
    """
    Create a function that can be used to lookup ADI values in your LARS application.
    
    Parameters:
    -----------
    results_df : pandas.DataFrame
        Results DataFrame from extract_latest_adi_values
    
    Returns:
    --------
    function
        A function that takes a pesticide name and returns its ADI value
    """
    
    # Create a dictionary for fast lookup
    adi_dict = {}
    for _, row in results_df.iterrows():
        if pd.notna(row['ADI_Value']):
            adi_dict[row['Pesticide'].lower()] = {
                'value': row['ADI_Value'],
                'unit': row['ADI_Unit'],
                'year': row['Year']
            }
    
    def get_adi(pesticide_name):
        """
        Get ADI value for a pesticide.
        
        Parameters:
        -----------
        pesticide_name : str
            Name of the pesticide
        
        Returns:
        --------
        dict or None
            Dictionary with keys: 'value', 'unit', 'year'
            Returns None if pesticide not found
        """
        return adi_dict.get(pesticide_name.lower())
    
    return get_adi

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Your pesticide list
    pesticide_list = [
        "abamectin", "aceatamiprid", "afla", "azoxystrobin", "bifenazate", 
        "bifenthrin", "boscalid", "buprofezin", "carbaryl", "carbendazim", 
        "carbofuran", "chlorantraniliprole", "chlorfenapyr", "chlorpyriphos", 
        "clothianidin", "cyanantraniliprole", "cyflufenamid", "cyflulthrin", 
        "cyflumetofen", "cyhalothrin", "cypermethrin", "cyprodianil", 
        "deltamethrin", "diazinon", "difenoconazole", "diflubenzoran", 
        "dimethomorph", "dinotefuran", "ethion", "ethofumesite", "etoxazole", 
        "famoxadon", "fenazaquin", "fenhexamide", "fenpyroxymate", "fipronil", 
        "fludioxonil", "flumetaquin", "fluopyram", "flutriafol", "hexythiazox", 
        "imidaclopride", "indoxacarb", "linuron", "malathion", "mandipropamid", 
        "metalaxyl", "methomyl", "methoxyfenozide", "metrafenon", 
        "mrthoxyfenoxide", "myclobutanil", "ometheoate", "penconazole", 
        "phoxim", "pipronyl butoxide", "pirimiphos", "pirimiphos methyl", 
        "profenofos", "propamocarb", "propiconazole", "pyraclostrobin", 
        "pyridaben", "pyrimethanil", "pyriproxyfen", "spinosad a", 
        "spinosad d", "spiromesfin", "spirotetramate", "sulfoxaflor", 
        "tebuconazole", "thiabendazole", "thiamethoxam", "thiaophonat-methyl", 
        "thiopendazole", "thiophonat methyl", "thiophonate", "tricyclazole", 
        "trifloxystrobin"
    ]
    
    # Path to your OpenFoodTox file
    file_path = "/Users/a12/Buraidah_lars/src/LARS/data/ReferenceValues_KJ_2023.xlsx"  # Update this path
    
    # Extract ADI values
    print("EXTRACTING ADI VALUES FROM OPENFOODTOX DATABASE")
    print("=" * 80)
    
    results_df = extract_latest_adi_values(pesticide_list, file_path)
    
    # Export results
    export_results(results_df, output_format='excel')
    
    # Create a lookup function for use in your LARS application
    get_adi = create_adi_lookup_function(results_df)
    
    # Example of how to use the lookup function
    print("\n" + "=" * 80)
    print("EXAMPLE USAGE OF THE ADI LOOKUP FUNCTION:")
    print("=" * 80)
    
    test_pesticides = ["chlorpyriphos", "deltamethrin", "imidaclopride", "xyz123"]
    for test in test_pesticides:
        adi_info = get_adi(test)
        if adi_info:
            print(f"{test:20s} → ADI: {adi_info['value']} {adi_info['unit']} (Year: {adi_info['year']})")
        else:
            print(f"{test:20s} → NO ADI FOUND")
    
    # Generate code snippet for integration into LARS
    print("\n" + "=" * 80)
    print("CODE FOR INTEGRATION INTO LARS:")
    print("=" * 80)
    
    integration_code = """
# ============================================================================
# INTEGRATION INTO LARS - ADI LOOKUP MODULE
# ============================================================================

class ADILookup:
    \"\"\"ADI lookup module for LARS application.\"\"\"
    
    def __init__(self, adi_dataframe):
        \"\"\"Initialize with ADI DataFrame.\"\"\"
        self.adi_dict = {}
        for _, row in adi_dataframe.iterrows():
            if pd.notna(row['ADI_Value']):
                self.adi_dict[row['Pesticide'].lower()] = {
                    'value': row['ADI_Value'],
                    'unit': row['ADI_Unit'],
                    'year': row['Year'],
                    'author': row['Author']
                }
    
    def get_adi(self, pesticide_name):
        \"\"\"Get ADI value for a pesticide.\"\"\"
        return self.adi_dict.get(pesticide_name.lower())
    
    def calculate_hqc(self, pesticide_name, residue_concentration, 
                     consumption_rate, body_weight, population='general'):
        \"\"\"
        Calculate Hazard Quotient for chronic exposure.
        
        Parameters:
        -----------
        pesticide_name : str
            Name of the pesticide
        residue_concentration : float
            Residue concentration in mg/kg
        consumption_rate : float
            Food consumption rate in kg/day
        body_weight : float
            Body weight in kg
        population : str
            Population group (for future expansion)
        
        Returns:
        --------
        dict or None
            Dictionary with HQc calculation results
        \"\"\"
        adi_info = self.get_adi(pesticide_name)
        
        if not adi_info:
            return None
        
        # Calculate EDI (Estimated Daily Intake)
        edi = (residue_concentration * consumption_rate) / body_weight
        
        # Calculate HQc (Hazard Quotient chronic)
        hqc = edi / adi_info['value']
        
        return {
            'pesticide': pesticide_name,
            'edi': edi,
            'adi': adi_info['value'],
            'hqc': hqc,
            'unit': 'mg/kg bw/day',
            'interpretation': 'Risk acceptable' if hqc < 1 else 'Risk unacceptable'
        }

# Usage example in LARS:
# adi_lookup = ADILookup(results_df)
# hqc_result = adi_lookup.calculate_hqc('chlorpyriphos', 0.1, 0.00763, 53)
"""
    
    print(integration_code)