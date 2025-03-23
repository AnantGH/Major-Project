import numpy as np
import matplotlib.pyplot as plt

# Load data from CSV
print("Loading data from data1.csv...")
try:
    # Load the entire dataset - first column is signal, second is time
    data = np.loadtxt('data2.csv', delimiter=',')
    signal = data[:, 0]  # First column - voltage values
    time = data[:, 1]    # Second column - time values
    print(f"Loaded {len(signal)} samples")
    
    # Create the plot
    plt.figure(figsize=(12, 6))
    plt.plot(time, signal, 'b-', label='Reconstructed Signal')
    plt.grid(True, alpha=0.3)
    plt.xlabel('Time (s)')
    plt.ylabel('Voltage (V)')
    plt.title('Reconstructed Waveform from CSV Data')
    plt.legend()
    
    # Add some statistics to the plot
    max_voltage = np.max(signal)
    min_voltage = np.min(signal)
    plt.text(0.02, 0.98, f'Max: {max_voltage:.2f}V\nMin: {min_voltage:.2f}V', 
             transform=plt.gca().transAxes, verticalalignment='top')
 
   
    plt.show()
    
except Exception as e:
    print(f"Error loading or plotting data: {e}")


# import numpy as np
# import os

# def load_data(self):
#     """Load data from the CSV file, validate, and fix issues if needed."""
#     file_path = r'C:\Users\Anant Raj\Major Project\data1.csv'
#     cleaned_file_path = r'C:\Users\Anant Raj\Major Project\data_cleaned.csv'

#     try:
#         # Step 1: Inspect the raw file content
#         print("\n--- Inspecting Raw File Content ---")
#         with open(file_path, 'r', encoding='utf-8') as file:
#             for i, line in enumerate(file):
#                 print(f"Row {i + 1}: {line.strip()}")

#         # Step 2: Attempt to load raw data
#         print("\n--- Attempting to Load Raw Data ---")
#         data = np.genfromtxt(file_path, delimiter=',', dtype=float, encoding='utf-8', invalid_raise=False)
#         print(f"Raw data loaded from CSV (first 5 rows):\n{data[:5]}")

#         # Step 3: Check if the data is valid
#         if data.ndim != 2 or data.shape[1] < 2:
#             raise ValueError("Invalid CSV format: Ensure the file has at least two numeric columns.")

#         # Step 4: Assign signal and time to instance attributes
#         self.signal = data[:, 0]  # First column (voltage)
#         self.time = data[:, 1]    # Second column (time)

#         # Debugging: Print sample data
#         print(f"Loaded signal (first 5 values): {self.signal[:5]}")
#         print(f"Loaded time (first 5 values): {self.time[:5]}")

#     except Exception as e:
#         # Step 5: Handle errors and attempt to fix issues
#         print(f"\nError loading CSV: {e}")
#         print("--- Attempting to Fix Issues ---")
#         cleaned_data = []
#         try:
#             with open(file_path, 'r', encoding='utf-8') as infile:
#                 for i, line in enumerate(infile):
#                     try:
#                         # Attempt to parse each row into floats
#                         values = [float(x) for x in line.strip().split(',')]
#                         cleaned_data.append(values)
#                     except ValueError:
#                         print(f"Invalid row skipped (Row {i + 1}): {line.strip()}")

#             # Save the cleaned data to a new file
#             if cleaned_data:
#                 np.savetxt(cleaned_file_path, cleaned_data, delimiter=',', fmt='%g')
#                 print(f"Cleaned data saved to: {cleaned_file_path}")

#                 # Retry loading the cleaned file
#                 print("\n--- Reloading Cleaned Data ---")
#                 data = np.genfromtxt(cleaned_file_path, delimiter=',', dtype=float)
#                 print(f"Cleaned data loaded (first 5 rows):\n{data[:5]}")

#                 # Assign cleaned signal and time
#                 self.signal = data[:, 0]  # First column (voltage)
#                 self.time = data[:, 1]    # Second column (time)
#                 print(f"Loaded cleaned signal (first 5 values): {self.signal[:5]}")
#                 print(f"Loaded cleaned time (first 5 values): {self.time[:5]}")
#             else:
#                 raise ValueError("No valid rows found in the CSV file.")

#         except Exception as clean_error:
#             print(f"Error during cleaning process: {clean_error}")
#             self.signal = None
#             self.time = None

#     # Final Debug: Confirm whether data was loaded successfully
#     if self.signal is None or self.time is None:
#         print("\n--- Final Status: No Data Loaded ---")
#     else:
#         print("\n--- Final Status: Data Loaded Successfully ---")

