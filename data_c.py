import numpy as np
import matplotlib.pyplot as plt

sampling_rate = 1000000
amplitude = 3.3
duration = 1

time = np.linspace(0, 1, (duration*sampling_rate), False)
signal = amplitude * np.sin(2 * np.pi * 1000 * time)

print(f"Generated {len(time)} samples")

data = np.column_stack((signal, time))  
np.savetxt('data2.csv', data, delimiter=',')
print(f"Saved data to data1.csv")

plt.plot(time, signal, label ='Original Signal')
plt.xlabel('Time (s)')
plt.ylabel('Amplitude (V)')
plt.show()



