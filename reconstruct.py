import numpy as np
import matplotlib.pyplot as plt

# Load data from CSV
print("Loading data from data1.csv...")
try:
    # Load the entire dataset - first column is signal, second is time
    data = np.loadtxt('data1.csv', delimiter=',')
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