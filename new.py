# import numpy as np
# import matplotlib.pyplot as plt
#
# def generate_waveform(wave_type, frequency, time_array):
#
#     if (t=0,t)
#     if wave_type == 1:
#         return np.sin(2 * np.pi * frequency * time_array)
#     elif wave_type == 2:
#         return np.square(2 * np.pi * frequency * time_array)
#     elif wave_type == 3:
#         return np.sawtooth(2 * np.pi * frequency * time_array)
#     elif wave_type == 4:
#         return np.abs(np.sin(2 * np.pi * frequency * time_array))
#     else:
#         raise ValueError("Invalid wave type. Choose 1, 2, 3, or 4.")
#
# def main():
#
#     sampling_rate = 2000
#     t = np.linspace(0, 0.1, int(sampling_rate * 0.1), endpoint=False)
#
#     wave_type = int(input("Enter waveform type (1=Sine, 2=Square, 3=Sawtooth, 4=Absolute Sine): "))
#     frequency = float(input("Enter frequency (Hz): "))
#
#     # Generate waveform
#     waveform = generate_waveform(wave_type, frequency, t)
#
#     # Plot waveform
#     plt.plot(t, waveform)
#     plt.xlabel("Time (s)")
#     plt.ylabel("Amplitude")
#     plt.title(f"{['Sine', 'Square', 'Sawtooth', 'Absolute Sine'][wave_type-1]} Wave ({frequency} Hz)")
#     plt.grid(True)
#     plt.show()
#
# if __name__ == "__main__":
#     main()
#
# import numpy as np
# import matplotlib.pyplot as plt
# from matplotlib.animation import FuncAnimation
#
# # Parameters
# A = float(input("Enter the voltage of the sinusoidal signal"))  # Amplitude
# f = 20  # Frequency (Hz)
# duration = 5.0  # Duration in seconds
# sampling_rate = 100  # Samples per second
#
# # Generate initial time values
# t = np.linspace(0, duration, int(sampling_rate * duration), endpoint=False)
#
# # Calculate initial sine wave values
# y = A * np.sin(2 * np.pi * f * t)
#
# # Set up the plot
# fig, ax = plt.subplots()
# line, = ax.plot(t, y)
# ax.set_xlim(0, duration)
# ax.set_ylim(-1.5 * A, 1.5 * A)  # Provide some buffer around the amplitude
# ax.set_xlabel('Time (s)')
# ax.set_ylabel('Amplitude')
#
# # Function to update the plot
# def update(frame):
#     global t, y
#
#     # Calculate new time values (shift the existing ones and add a new point)
#     t = np.append(t[1:], t[-1] + 1/sampling_rate)
#
#     # Calculate new sine wave values
#     y = A * np.sin(2 * np.pi * f * t)
#
#     # Update the line data
#     line.set_data(t, y)
#
#     return line,
#
# # Create the animation
# ani = FuncAnimation(fig, update, frames=int(sampling_rate * duration), interval=1000/sampling_rate, blit=True)
#
# # Show the plot
# plt.show()

import numpy as np
import matplotlib.pyplot as plt

# Parameters
A = int(input("Enter the voltage of the incoming signal:"))  # Amplitude
f = 2  # Frequency (Hz)
duration = 5.0  # Duration in seconds
sampling_rate = 100  # Samples per second

# ser = serial.Serial('COM3', 9600)  # Replace 'COM3' with your actual port and 9600 with your baud rate
#
# # Read data from the UART (adjust data size as needed)
# data = ser.read(1024)

# Process the raw data
# data_str = data.decode()
# voltage_values = [float(value) for value in data_str.split(',')]
# data = np.array(voltage_values)

# Generate time values
t = np.linspace(0, duration, int(sampling_rate * duration), endpoint=False)

# Calculate sine wave values
y = A * np.sin(2 * np.pi * f * t)

# Set up the plot
plt.figure(figsize=(10, 6))  # Adjust figure size if needed
plt.plot(t, y)
plt.title('Sine Wave')
plt.xlabel('Time (s)')
plt.ylabel('Amplitude')
plt.grid(True)  # Add a grid for better visualization
plt.show()