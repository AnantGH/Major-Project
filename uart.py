import serial
import serial as ser
import numpy as np
import matplotlib.pyplot as plt

# Configure the serial port (adjust parameters as needed)
# ser = serial.Serial('COM3', 9600)  # Replace 'COM3' with your actual port and 9600 with your baud rate
#
# # Read data from the UART (adjust data size as needed)
# data = ser.read(1024)

# Process the raw data
# data_str = data.decode()
# voltage_values = [float(value) for value in data_str.split(',')]
# data = np.array(voltage_values)

#ASCII data to be inputted 45, 56, 89
# data_str = input("Enter comma-separated ASCII codes (e.g., 65, 72, 68): ")

# Extract numerical values (assuming comma-separated)
# values = [int(value) for value in data_str.split(',')]
from numpy import arange

fig, ax = plt.subplots()
x= np.arange(0,5,0.1)
y=np.sin(x)

line, = ax.plot(x,y)

def update(frame):
    y=np.sin(x+frame*0.1)
    line.set_ydata(y)
    return line,

plt.show()

