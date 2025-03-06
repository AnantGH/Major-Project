import sys
import serial
import serial.tools.list_ports
import numpy as np
import pandas as pd
import pyqtgraph as pg
import pyqtgraph.exporters
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QComboBox, QSpinBox, QTabWidget, QFileDialog, QHBoxLayout, QCheckBox,
    QDoubleSpinBox, QSlider, QGroupBox, QFormLayout, QScrollArea
)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QColor

class SerialReader(QThread):
    data_received = pyqtSignal(list)

    def __init__(self, port, baudrate, channels=4):
        super().__init__()
        self.channels = channels
        self.running = False
        self.port = port
        self.baudrate = baudrate
        try:
            self.ser = serial.Serial(port, baudrate)
            print(f"Connected to serial port: {port} at {baudrate} baud")
        except serial.SerialException as e:
            print(f"Error opening serial port: {e}")
            self.ser = None

    def run(self):
        if self.ser:
            self.running = True
            print("Starting serial data acquisition")
            while self.running:
                try:
                    if self.ser.in_waiting > 0:
                        # Read and parse data from serial (adjust based on your hardware's output format)
                        serial_data = self.ser.readline().decode('utf-8').strip()
                        # Assuming data is comma-separated, like "1.23,2.34,3.45,4.56"
                        try:
                            data = [float(val) for val in serial_data.split(',')]
                            self.data_received.emit(data)
                        except ValueError:
                            print(f"Invalid data received: {serial_data}")
                except serial.SerialException as e:
                    print(f"Serial read error: {e}")
                    self.running = False
                # No need for artificial sleep, serial read will handle timing

    def stop(self):
        self.running = False
        if self.ser:
            self.ser.close()
        self.quit()
        self.wait()

    def set_ch1_amplitude(self, amplitude):
        self.ch1_amplitude = amplitude
        if not self.use_dummy and self.serial and self.serial.is_open:
            try:
                command = f"CH1AMP,{amplitude:.1f}\n"  # Customize based on hardware protocol
                self.serial.write(command.encode('utf-8'))
                print(f"Set CH1 amplitude to {amplitude}V")
            except serial.SerialException as e:
                print(f"Error setting CH1 amplitude: {e}")

class PlotWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Waveform Display")
        self.setGeometry(200, 200, 900, 600)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setTitle("Oscilloscope Signal")
        self.plot_widget.setLabel('left', 'Voltage', 'V')
        self.plot_widget.setLabel('bottom', 'Time', 'ms')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setBackground('#000A1E')
        self.setCentralWidget(self.plot_widget)
        colors = ['#FF0000', '#00FF00', '#33CCFF', '#FFFF00']
        self.traces = [self.plot_widget.plot([], [], pen=pg.mkPen(color=color, width=2)) for color in colors]

    def update_plot(self, data_buffer, channel_active, time_div, voltage_div, display_window, sample_rate, channel_positions, horizontal_position):
        for i, trace in enumerate(self.traces):
            if channel_active[i] and data_buffer[i]:
                num_points = min(len(data_buffer[i]), display_window)
                x_values = np.linspace(0, num_points * (1000 / sample_rate) / (time_div * 10), num_points)
                x_values += horizontal_position * (1000 / sample_rate) / (time_div * 10)
                y_values = np.array(data_buffer[i][-num_points:]) * voltage_div + channel_positions[i]
                trace.setData(x_values, y_values)
            else:
                trace.setData([], [])
        self.plot_widget.setXRange(horizontal_position * (1000 / sample_rate) / (time_div * 10),
                                   horizontal_position * (1000 / sample_rate) / (time_div * 10) + 
                                   display_window * (1000 / sample_rate) / (time_div * 10))

class OscilloscopeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Oscilloscope")
        self.setGeometry(100, 100, 1200, 800)

        self.data_buffer = [[] for _ in range(4)]
        self.max_samples = 200
        self.display_window = 100
        self.sample_rate = 20
        self.serial_thread = None
        self.channel_active = [True, True, True, True]
        self.channel_positions = [0, 0, 0, 0]
        self.horizontal_position = 0
        self.is_running = False
        self.plot_window = None
        self.initUI()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)

    def initUI(self):
        self.setStyleSheet("""
            QWidget { background-color: #121212; color: #ffffff; }
            QGroupBox { border: 1px solid #555; border-radius: 5px; margin-top: 1ex; padding: 10px; font-weight: bold; color: #ffffff; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }
            QLabel { color: #ffffff; }
            QComboBox, QSpinBox, QDoubleSpinBox { background-color: #2c2c2c; color: #ffffff; border: 1px solid #555; border-radius: 3px; padding: 2px; }
            QComboBox::drop-down { border: 0px; width: 20px; background-color: #2c2c2c; }
            QComboBox::down-arrow { image: url(:/qt-project.org/styles/commonstyle/images/downarrow-ffffff-20.png); }
            QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { background-color: #2c2c2c; border: 1px solid #555; width: 16px; }
            QSlider::groove:horizontal { border: 1px solid #999; height: 8px; background: #333; margin: 2px 0; }
            QSlider::handle:horizontal { background: #fff; border: 1px solid #777; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
            QSlider::add-page:horizontal { background: #555; }
            QSlider::sub-page:horizontal { background: #777; }
            QCheckBox { color: #ffffff; }
            QPushButton { padding: 10px; border-radius: 3px; color: #ffffff; }
            QPushButton#start_button { background-color: #1E88E5; }
            QPushButton#stop_button { background-color: #D32F2F; }
            QPushButton#run_button { background-color: #FF9800; }
            QPushButton#auto_set_button { background-color: #FF5722; }
            QPushButton#default_button { background-color: #9E9E9E; }
            QPushButton#save_button { background-color: #388E3C; }
            QPushButton#record_button {background-color:#90bf43; }
            QTabWidget { background-color: #121212; }
            QTabBar::tab { background-color: #2c2c2c; color: #ffffff; padding: 10px; margin-right: 2px; border: 1px solid #555; border-bottom: none; border-top-left-radius: 3px; border-top-right-radius: 3px; }
            QTabBar::tab:selected { background-color: #1E88E5; color: #ffffff; }
        """)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Add scroll area for controls
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #121212;")
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        control_layout.setSpacing(15)

        # Define colors for channels
        colors = ['#FF0000', '#00FF00', '#33CCFF', '#FFFF00']

        # Tabbed Interface
        self.tabs = QTabWidget()
        self.main_tab = QWidget()
        self.fft_tab = QWidget()
        self.tabs.addTab(self.main_tab, "Oscilloscope")
        self.tabs.addTab(self.fft_tab, "FFT Analysis")
        control_layout.addWidget(self.tabs)

        self.main_layout = QVBoxLayout()
        self.fft_layout = QVBoxLayout()
        self.main_tab.setLayout(self.main_layout)
        self.fft_tab.setLayout(self.fft_layout)

        # Connectivity Controls
        connectivity_group = QGroupBox("Connectivity")
        connectivity_layout = QHBoxLayout()
        self.com_label = QLabel("Select COM Port:")
        connectivity_layout.addWidget(self.com_label)
        self.com_port_selector = QComboBox()
        self.populate_com_ports()
        connectivity_layout.addWidget(self.com_port_selector)
        self.baud_label = QLabel("Baud Rate:")
        connectivity_layout.addWidget(self.baud_label)
        self.baud_selector = QSpinBox()
        self.baud_selector.setRange(9600, 1152000)
        self.baud_selector.setValue(115200)
        connectivity_layout.addWidget(self.baud_selector)
        connectivity_group.setLayout(connectivity_layout)
        self.main_layout.addWidget(connectivity_group)

        # Display Controls
        display_group = QGroupBox("Display Controls")
        display_layout = QFormLayout()
        self.intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self.intensity_slider.setRange(10, 100)
        self.intensity_slider.setValue(100)
        self.intensity_slider.valueChanged.connect(self.update_intensity)
        display_layout.addRow("Intensity:", self.intensity_slider)
        self.grid_check = QCheckBox("Grid")
        self.grid_check.setChecked(True)
        self.grid_check.stateChanged.connect(self.toggle_grid)
        display_layout.addRow(self.grid_check)
        display_group.setLayout(display_layout)
        self.main_layout.addWidget(display_group)

        # Vertical Controls
        vertical_group = QGroupBox("Vertical Controls")
        vertical_layout = QVBoxLayout()
        self.channel_selector = QComboBox()
        self.channel_selector.addItems(["CH1", "CH2", "CH3", "CH4"])
        vertical_layout.addWidget(self.channel_selector)
        self.volt_div_spinbox = QDoubleSpinBox()
        self.volt_div_spinbox.setMinimum(0.1)
        self.volt_div_spinbox.setMaximum(10)
        self.volt_div_spinbox.setValue(1)
        vertical_layout.addWidget(QLabel("Volts/Div:"))
        vertical_layout.addWidget(self.volt_div_spinbox)
        self.pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.pos_slider.setRange(-100, 100)
        self.pos_slider.setValue(0)
        self.pos_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #999;
                height: 8px;
                background: #333;
                margin: 2px 0;
            }
            QSlider::handle:horizontal {
                background: #fff;
                border: 1px solid #777;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::add-page:horizontal {
                background: #555;
            }
            QSlider::sub-page:horizontal {
                background: #777;
            }
        """)
        self.pos_slider.valueChanged.connect(self.update_vertical_position)
        vertical_layout.addWidget(QLabel("Position:"))
        vertical_layout.addWidget(self.pos_slider)
        self.coupling_combo = QComboBox()
        self.coupling_combo.addItems(["AC", "DC", "GND"])
        vertical_layout.addWidget(QLabel("Coupling:"))
        vertical_layout.addWidget(self.coupling_combo)
        vertical_group.setLayout(vertical_layout)
        self.main_layout.addWidget(vertical_group)  # Changed to self.main_layout

        # Horizontal Controls
        horizontal_group = QGroupBox("Horizontal Controls")
        horizontal_layout = QFormLayout()
        self.time_div_spinbox = QDoubleSpinBox()
        self.time_div_spinbox.setMinimum(0.1)
        self.time_div_spinbox.setMaximum(10)
        self.time_div_spinbox.setValue(1)
        horizontal_layout.addRow("Time/Div:", self.time_div_spinbox)
        self.horiz_pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.horiz_pos_slider.setRange(-50, 50)
        self.horiz_pos_slider.setValue(0)
        self.horiz_pos_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #999;
                height: 8px;
                background: #333;
                margin: 2px 0;
            }
            QSlider::handle:horizontal {
                background: #fff;
                border: 1px solid #777;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::add-page:horizontal {
                background: #555;
            }
            QSlider::sub-page:horizontal {
                background: #777;
            }
        """)
        self.horiz_pos_slider.valueChanged.connect(self.update_horizontal_position)
        horizontal_layout.addRow("Position:", self.horiz_pos_slider)
        horizontal_group.setLayout(horizontal_layout)
        self.main_layout.addWidget(horizontal_group)  # Changed to self.main_layout
        # Trigger Controls
        trigger_group = QGroupBox("Trigger Controls")
        trigger_layout = QFormLayout()
        self.trigger_spinbox = QDoubleSpinBox()
        self.trigger_spinbox.setRange(0, 5000)
        self.trigger_spinbox.setValue(2500)
        trigger_layout.addRow("Trigger Level:", self.trigger_spinbox)
        self.trigger_mode_combo = QComboBox()
        self.trigger_mode_combo.addItems(["Auto", "Normal", "Single"])
        self.trigger_mode_combo.currentTextChanged.connect(self.update_trigger_mode)
        trigger_layout.addRow("Mode:", self.trigger_mode_combo)
        self.trigger_source_combo = QComboBox()
        self.trigger_source_combo.addItems(["CH1", "CH2", "CH3", "CH4", "External"])
        trigger_layout.addRow("Source:", self.trigger_source_combo)
        self.trigger_slope_combo = QComboBox()
        self.trigger_slope_combo.addItems(["Rising", "Falling"])
        trigger_layout.addRow("Slope:", self.trigger_slope_combo)
        self.trigger_holdoff_spinbox = QDoubleSpinBox()
        self.trigger_holdoff_spinbox.setRange(0, 1000)
        self.trigger_holdoff_spinbox.setValue(0)
        trigger_layout.addRow("Holdoff (ms):", self.trigger_holdoff_spinbox)
        trigger_group.setLayout(trigger_layout)
        self.main_layout.addWidget(trigger_group)

        # Input Controls
        input_group = QGroupBox("Input Controls")
        input_layout = QFormLayout()
        self.probe_attenuation_combo = QComboBox()
        self.probe_attenuation_combo.addItems(["1x", "10x"])
        input_layout.addRow("Probe Attenuation:", self.probe_attenuation_combo)
        self.impedance_combo = QComboBox()
        self.impedance_combo.addItems(["1 MΩ", "50 Ω"])
        input_layout.addRow("Impedance:", self.impedance_combo)
        input_group.setLayout(input_layout)
        self.main_layout.addWidget(input_group)

        # Measurement Controls
        measure_group = QGroupBox("Measurements")
        measure_layout = QVBoxLayout()
        self.measure_freq = QLabel("Frequency: N/A")
        measure_layout.addWidget(self.measure_freq)
        self.measure_rms = QLabel("RMS Voltage: N/A")
        measure_layout.addWidget(self.measure_rms)
        measure_group.setLayout(measure_layout)
        self.main_layout.addWidget(measure_group)

        # Utility Controls
        utility_group = QGroupBox("Utility")
        utility_layout = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setStyleSheet("background-color: #1E88E5; color: white; padding: 10px;")
        self.start_button.clicked.connect(self.start_acquisition)
        utility_layout.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet("background-color: #D32F2F; color: white; padding: 10px;")
        self.stop_button.clicked.connect(self.stop_acquisition)
        utility_layout.addWidget(self.stop_button)
        self.run_button = QPushButton("Run")
        self.run_button.setStyleSheet("background-color: #FF9800; color: white; padding: 10px;")
        self.run_button.clicked.connect(self.run_plot)
        utility_layout.addWidget(self.run_button)
        self.auto_set_button = QPushButton("Auto Set")
        self.auto_set_button.setStyleSheet("background-color: #FF5722; color: white; padding: 10px;")
        self.auto_set_button.clicked.connect(self.auto_set)
        utility_layout.addWidget(self.auto_set_button)
        self.default_button = QPushButton("Default Setup")
        self.default_button.setStyleSheet("background-color: #9E9E9E; color: white; padding: 10px;")
        self.default_button.clicked.connect(self.default_setup)
        utility_layout.addWidget(self.default_button)
        self.save_button = QPushButton("Save Snapshot")
        self.save_button.setStyleSheet("background-color: #388E3C; color: white; padding: 10px;")
        self.save_button.clicked.connect(self.save_data)
        utility_layout.addWidget(self.save_button)
        utility_group.setLayout(utility_layout)
        control_layout.addWidget(utility_group)
        self.record_button = QPushButton("Record Waveform")
        self.record_button.setStyleSheet("background-color: #90bf43; color: white; padding: 10px;")
        self.record_button.clicked.connect(self.record_data)
        utility_layout.addWidget(self.record_button)
        utility_group.setLayout(utility_layout)
        control_layout.addWidget(utility_group)


        # Channel Controls
        channel_controls_layout = QHBoxLayout()
        self.channel_checkboxes = []
        for i in range(4):
            checkbox = QCheckBox(f"CH{i+1}")
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(lambda state, idx=i: self.toggle_channel(idx, state))
            checkbox.setStyleSheet(f"color: {colors[i]};")
            self.channel_checkboxes.append(checkbox)
            channel_controls_layout.addWidget(checkbox)
        self.main_layout.addLayout(channel_controls_layout)



        control_layout.addStretch()  # Push controls to top
        scroll.setWidget(control_widget)
        main_layout.addWidget(scroll)

    def toggle_channel(self, channel_idx, state):
        self.channel_active[channel_idx] = bool(state)
        self.update_plot()

    def populate_com_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.com_port_selector.clear()
        self.com_port_selector.addItems(ports if ports else ["No Ports Found"])

    def update_plot(self):
        if not self.plot_window:
            return

        time_div = self.time_div_spinbox.value()
        voltage_div = self.volt_div_spinbox.value()
        trigger_level = self.trigger_spinbox.value()
        trigger_source = self.trigger_source_combo.currentIndex()
        trigger_slope = self.trigger_slope_combo.currentText()

        triggered = False
        if self.is_running and self.trigger_mode_combo.currentText() == "Normal":
            for i, buffer in enumerate(self.data_buffer):
                if i == trigger_source and buffer and self.channel_active[i]:
                    last_val = buffer[-2] if len(buffer) > 1 else buffer[-1]
                    curr_val = buffer[-1]
                    if (trigger_slope == "Rising" and last_val < trigger_level <= curr_val) or \
                       (trigger_slope == "Falling" and last_val > trigger_level >= curr_val):
                        triggered = True
                        break
            if not triggered:
                return

        self.plot_window.update_plot(self.data_buffer, self.channel_active, time_div, voltage_div, 
                                     self.display_window, self.sample_rate, self.channel_positions, 
                                     self.horizontal_position)

        if self.data_buffer[0]:
            freq = self.calculate_frequency(self.data_buffer[0])
            rms = np.sqrt(np.mean(np.square(self.data_buffer[0][-self.display_window:])))
            self.measure_freq.setText(f"Frequency: {freq:.2f} Hz")
            self.measure_rms.setText(f"RMS Voltage: {rms:.2f} V")

    def calculate_frequency(self, buffer):
        if len(buffer) < 2:
            return 0
        crossings = 0
        for i in range(1, min(len(buffer), self.display_window)):
            if (buffer[i-1] < 0 and buffer[i] >= 0) or (buffer[i-1] > 0 and buffer[i] <= 0):
                crossings += 1
        return crossings / (self.display_window * (1000 / self.sample_rate) / 1000.0) / 2.0

    def start_acquisition(self):
        if not self.serial_thread:
            port = self.com_port_selector.currentText()
            baudrate = self.baud_selector.value()
            self.serial_thread = SerialReader(port, baudrate, channels=4)
            self.serial_thread.data_received.connect(self.process_data)
            self.serial_thread.start()
            self.is_running = True
            if self.plot_window:
                self.timer.start(50)

    def stop_acquisition(self):
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread = None
        self.is_running = False
        self.timer.stop()
        if self.plot_window:
            self.plot_window.update_plot(self.data_buffer, self.channel_active, 
                                        self.time_div_spinbox.value(), self.volt_div_spinbox.value(),
                                        self.display_window, self.sample_rate, 
                                        self.channel_positions, self.horizontal_position)

    def process_data(self, data):
        for i in range(min(len(data), len(self.data_buffer))):
            self.data_buffer[i].append(data[i])
            if len(self.data_buffer[i]) > self.max_samples:
                self.data_buffer[i].pop(0)
        if self.is_running and self.plot_window:
            self.update_plot()

    def change_time_division(self, delta):
        new_val = self.time_div_spinbox.value() + delta
        if 0.1 <= new_val <= self.time_div_spinbox.maximum():
            self.time_div_spinbox.setValue(new_val)
            self.update_plot()

    def change_voltage_division(self, delta):
        new_val = self.volt_div_spinbox.value() + delta
        if 0.1 <= new_val <= self.volt_div_spinbox.maximum():
            self.volt_div_spinbox.setValue(new_val)
            self.update_plot()

    def apply_trigger(self):
        if self.plot_window:
            self.update_plot()

    def save_data(self):
        print("Save Snapshot button clicked")
        if not self.plot_window:
            print("Please open the plot window first using the 'Run' button")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Save Snapshot", "", "PNG Files (*.png);;JPG Files (*.jpg);;All Files (*)")
        print(f"Selected filename: {filename}")
        if filename:
            try:
                if not (filename.endswith('.png') or filename.endswith('.jpg')):
                    filename += '.png'
                exporter = pg.exporters.ImageExporter(self.plot_window.plot_widget.plotItem)
                exporter.parameters()['width'] = 900
                exporter.export(filename)
                print(f"Snapshot saved to {filename}")
            except PermissionError:
                print(f"Permission denied: Cannot write to {filename}")
            except Exception as e:
                print(f"Error saving snapshot: {e}")

    def update_coupling(self, text):
        print(f"Coupling set to {text} for {self.channel_selector.currentText()}")

    def update_vertical_position(self, value):
        channel = self.channel_selector.currentIndex()
        self.channel_positions[channel] = value
        self.update_plot()

    def update_horizontal_position(self, value):
        self.horizontal_position = value
        self.update_plot()

    def update_trigger_mode(self, mode):
        if mode == "Single" and self.is_running and self.plot_window:
            self.timer.stop()
        elif mode in ["Auto", "Normal"] and not self.is_running and self.plot_window:
            self.timer.start(50)

    def run_plot(self):
        if not self.plot_window:
            self.plot_window = PlotWindow(self)
            self.plot_window.show()
            self.update_plot()

    def auto_set(self):
        print("Auto Set triggered")

    def default_setup(self):
        self.time_div_spinbox.setValue(1)
        self.volt_div_spinbox.setValue(1)
        self.trigger_spinbox.setValue(2500)
        self.trigger_mode_combo.setCurrentText("Auto")
        self.trigger_source_combo.setCurrentText("CH1")
        self.trigger_slope_combo.setCurrentText("Rising")
        self.trigger_holdoff_spinbox.setValue(0)
        self.pos_slider.setValue(0)
        self.horiz_pos_slider.setValue(0)
        self.channel_active = [True, True, True, True]
        for checkbox in self.channel_checkboxes:
            checkbox.setChecked(True)
        self.update_plot()

    def update_intensity(self, value):
        if not self.plot_window:
            return
        alpha = value / 100.0
        for trace in self.plot_window.traces:
            color = QColor(trace.opts['pen'].color())
            color.setAlphaF(alpha)
            trace.setPen(pg.mkPen(color=color, width=2))
        self.update_plot()

    def record_data(self):
        print("Record Waveform button clicked")
        filename, _ = QFileDialog.getSaveFileName(self, "Save Waveform Data", "", "CSV Files (*.csv);;All Files (*)")
        print(f"Selected filename: {filename}")
        if filename:
            if not filename.endswith('.csv'):
                filename += '.csv'
            try:
                # Prepare data for CSV
                max_length = max(len(buffer) for buffer in self.data_buffer if buffer)
                if max_length == 0:
                    print("No data to save - all channels are empty")
                    with open(filename, 'w') as file:
                        file.write("No data available\n")
                    return

                # Create a dictionary to hold the data for each active channel
                data_dict = {}
                for i, buffer in enumerate(self.data_buffer):
                    if self.channel_active[i]:
                        data_dict[f"Channel {i+1}"] = buffer + [0.0] * (max_length - len(buffer)) if buffer else [0.0] * max_length

                # If no active channels have data, write a message
                if not data_dict:
                    print("No active channels have data to save")
                    with open(filename, 'w') as file:
                        file.write("No active channels have data\n")
                    return

                # Convert to DataFrame and save to CSV
                df = pd.DataFrame(data_dict)
                df.to_csv(filename, index_label="Sample")
                print(f"Waveform data saved to {filename}")
            except PermissionError:
                print(f"Permission denied: Cannot write to {filename}")
            except Exception as e:
                print(f"Error saving waveform data: {e}")

    def toggle_grid(self, state):
        if self.plot_window:
            self.plot_window.plot_widget.showGrid(x=state, y=state, alpha=0.3)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = OscilloscopeApp()
    window.show()
    sys.exit(app.exec())