import tkinter as tk
from tkinter import ttk
import threading
import time
import random

class Oscilloscope(tk.Tk):
    def __init__(self):
        super().__init__()

        # Window setup
        self.title("Virtual Oscilloscope")
        self.geometry("800x600")
        self.resizable(False, False)

        # Oscilloscope parameters
        self.time_div = 1       # Time division (ms/div)
        self.voltage_div = 1    # Voltage division (V/div)
        self.running = True
        self.waveform_type = 'Sine'
        self.data = []

        # Create UI components
        self.create_widgets()

        # Start data acquisition in a separate thread
        self.acquire_thread = threading.Thread(target=self.acquire_data)
        self.acquire_thread.start()

        # Update the plot continuously
        self.update_plot()

    def create_widgets(self):
        # Canvas for plotting the waveform
        self.canvas = tk.Canvas(self, bg='black', width=800, height=500)
        self.canvas.pack()

        # Control panel
        control_frame = tk.Frame(self)
        control_frame.pack(fill='x')

        # Time Division Control
        tk.Label(control_frame, text="Time/Div (ms):").pack(side='left', padx=5)
        self.time_div_slider = tk.Scale(control_frame, from_=1, to=10, orient='horizontal', command=self.update_time_div)
        self.time_div_slider.set(self.time_div)
        self.time_div_slider.pack(side='left')

        # Voltage Division Control
        tk.Label(control_frame, text="Voltage/Div (V):").pack(side='left', padx=5)
        self.voltage_div_slider = tk.Scale(control_frame, from_=1, to=10, orient='horizontal', command=self.update_voltage_div)
        self.voltage_div_slider.set(self.voltage_div)
        self.voltage_div_slider.pack(side='left')

        # Waveform Selection
        tk.Label(control_frame, text="Waveform:").pack(side='left', padx=5)
        self.waveform_combo = ttk.Combobox(control_frame, values=['Sine', 'Square', 'Triangle'], state='readonly')
        self.waveform_combo.current(0)
        self.waveform_combo.bind('<<ComboboxSelected>>', self.update_waveform)
        self.waveform_combo.pack(side='left')

    def update_time_div(self, value):
        self.time_div = int(value)

    def update_voltage_div(self, value):
        self.voltage_div = int(value)

    def update_waveform(self, event):
        self.waveform_type = self.waveform_combo.get()

    def acquire_data(self):
        while self.running:
            # Simulate data acquisition
            value = self.get_signal_value()
            self.data.append(value)
            if len(self.data) > 800:
                self.data.pop(0)
            time.sleep(0.01 * self.time_div)

    def get_signal_value(self):
        # Replace this method with actual USART data reading
        t = time.time()
        if self.waveform_type == 'Sine':
            return self.voltage_div * random.uniform(-1, 1)
        elif self.waveform_type == 'Square':
            return self.voltage_div if random.choice([True, False]) else -self.voltage_div
        elif self.waveform_type == 'Triangle':
            return self.voltage_div * (abs((t % 2) - 1) * 2 - 1)
        else:
            return 0

    def update_plot(self):
        self.canvas.delete('all')
        self.draw_grid()
        self.draw_waveform()
        self.after(50, self.update_plot)

    def draw_grid(self):
        # Draw vertical grid lines
        for i in range(0, 800, 50):
            color = 'gray' if i % 100 else 'white'
            self.canvas.create_line(i, 0, i, 500, fill=color)
        # Draw horizontal grid lines
        for i in range(0, 500, 50):
            color = 'gray' if i % 100 else 'white'
            self.canvas.create_line(0, i, 800, i, fill=color)

    def draw_waveform(self):
        if len(self.data) > 1:
            scale_x = 800 / len(self.data)
            scale_y = 50 / self.voltage_div
            for i in range(len(self.data) - 1):
                x1 = i * scale_x
                y1 = 250 - (self.data[i] * scale_y)
                x2 = (i + 1) * scale_x
                y2 = 250 - (self.data[i + 1] * scale_y)
                self.canvas.create_line(x1, y1, x2, y2, fill='yellow')

    def on_closing(self):
        self.running = False
        self.acquire_thread.join()
        self.destroy()

if __name__ == '__main__':
    app = Oscilloscope()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
