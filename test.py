import sys
import serial
import serial.tools.list_ports
import numpy as np
import pandas as pd
import pyqtgraph as pg
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QComboBox, QSpinBox, QTabWidget, QFileDialog, QHBoxLayout, QCheckBox,
    QDoubleSpinBox, QSlider, QGroupBox, QFormLayout, QScrollArea, QGridLayout  # Added QGridLayout
)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QColor
from pyqtgraph.exporters import ImageExporter

class SerialReader(QThread):
    data_received = pyqtSignal(list)

    def __init__(self, channels=4, impedance=1e6):  # Removed ch1_amplitude
        super().__init__()
        self.channels = channels
        self.running = False
        self.impedance = impedance
        self.signal_buffers = [[] for _ in range(channels)]
        self.coupling_modes = ['DC'] * channels  # DC coupling is default
        self.data_index = 0
        
        # Load CSV data
        try:
            # Read CSV and convert string pairs to numerical values
            with open(r"C:\Users\Anant Raj\Major Project\data.csv", 'r') as file:
                lines = file.readlines()
                self.csv_data = []
                for line in lines:
                    # Remove brackets and split time,voltage pairs
                    clean_line = line.strip('[\n]').split(',')
                    if len(clean_line) == 2:
                        try:
                            time = float(clean_line[0])                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     
                            voltage = float(clean_line[1])
                            self.csv_data.append([time, voltage])
                        except ValueError:
                            continue
                
            print(f"Loaded {len(self.csv_data)} samples from CSV")
        except Exception as e:
            print(f"Error loading CSV: {e}")
            self.csv_data = None

    def run(self):
        if self.csv_data is None:
            return

        self.running = True
        batch_size = 1000
        buffer_size = 500
        
        while self.running:
            try:
                data_batch = [0.0] * self.channels  # Initialize with zeros for all channels
                
                if self.data_index >= len(self.csv_data):
                    self.data_index = 0
                    
                # Get voltage for Channel 1 only
                voltage = self.csv_data[self.data_index][1]
                
                # Process Channel 1 data
                if self.coupling_modes[0] == 'AC':
                    self.signal_buffers[0].append(voltage)
                    if len(self.signal_buffers[0]) > 100:
                        self.signal_buffers[0].pop(0)
                    dc_offset = np.mean(self.signal_buffers[0])
                    voltage -= dc_offset
                elif self.coupling_modes[0] == 'GND':
                    voltage = 0.0
                
                data_batch[0] = voltage  # Set Channel 1 value
                self.data_received.emit(data_batch)  # Emit single data point
                self.data_index += 1
                
                time.sleep(0.001)  # Small delay between points
                    
            except Exception as e:
                print(f"Error processing data: {e}")
                self.running = False

    def stop(self):
        self.running = False
        self.quit()
        self.wait()

    def set_impedance(self, impedance):
        self.impedance = impedance

    def set_channel_coupling(self, channel, mode):
        """Set coupling mode for a specific channel"""
        if 0 <= channel < self.channels:
            self.coupling_modes[channel] = mode
            self.signal_buffers[channel].clear()

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

    def update_plot(self, data_buffer, channel_active, time_div, voltage_div, display_window, 
                   sample_rate, channel_positions, horizontal_position, probe_attenuation):
        # Calculate time base
        total_div = 10  # Standard oscilloscope has 10 divisions
        display_window_time = time_div * total_div  # Total time window
        
        for i, trace in enumerate(self.traces):
            if channel_active[i] and data_buffer[i]:
                num_points = min(len(data_buffer[i]), display_window)
                
                # Generate time values (x-axis) with proper scaling for horizontal movement
                time_per_point = time_div / (num_points / total_div)
                x_values = np.arange(num_points) * time_per_point
                x_values = x_values - (horizontal_position * time_div)  # Apply horizontal shift
                
                # Scale voltage values (y-axis)
                y_values = np.array(data_buffer[i][-num_points:])
                y_values = y_values / probe_attenuation
                y_values = y_values + (channel_positions[i] / 100.0 * 8 * voltage_div)
                
                trace.setData(x_values, y_values)
            else:
                trace.setData([], [])

        # Set view ranges to match time divisions
        self.plot_widget.setXRange(
            -time_div * 5,  # Show 5 divisions before center
            time_div * 5    # Show 5 divisions after center
        )
        self.plot_widget.setYRange(-4 * voltage_div, 4 * voltage_div)

class OscilloscopeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Oscilloscope")
        self.setGeometry(100, 100, 1200, 800)
        self.data_buffer = [[] for _ in range(4)]
        self.max_samples = 500
        self.display_window = 500
        self.sample_rate = 100
        self.serial_thread = None
        self.channel_active = [True, False, False, False]  # Only CH1 active by default
        self.channel_positions = [0, 0, 0, 0]
        self.horizontal_position = 0
        self.is_running = False
        self.plot_window = None
        self.ch1_amplitude = 2.5
        self.probe_attenuation = 1.0
        self.impedance = 1e6
        self.initUI()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)

    def initUI(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0f172a;  /* Dark blue background */
                color: #e2e8f0;
            }
            QGroupBox {
                background-color: #1e293b;  /* Slightly lighter blue */
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 1ex;
                padding: 12px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #60a5fa;  /* Bright blue for titles */
            }
            QLabel {
                color: #e2e8f0;
                font-weight: 500;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #293548;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px;
                min-height: 24px;
            }
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
                background-color: #334155;
                border-color: #60a5fa;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);  /* Lighten effect on hover */
                margin-top: -1px;  /* Slight lift effect */
                margin-bottom: 1px;
            }
            QPushButton#start_button { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
            }
            QPushButton#start_button:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #60a5fa, stop:1 #3b82f6);
            }
            QPushButton#stop_button { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ef4444, stop:1 #dc2626);
            }
            QPushButton#stop_button:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f87171, stop:1 #ef4444);
            }
            QPushButton#run_button { 
                background: linear-gradient(135deg, #f59e0b, #d97706);
            }
            QPushButton#auto_set_button { 
                background: linear-gradient(135deg, #8b5cf6, #7c3aed);
            }
            QPushButton#default_button { 
                background: linear-gradient(135deg, #64748b, #475569);
            }
            QPushButton#save_button { 
                background: linear-gradient(135deg, #22c55e, #16a34a);
            }
            QPushButton#record_button { 
                background: linear-gradient(135deg, #06b6d4, #0891b2);
            }
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #334155;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #60a5fa;
                border: 2px solid #3b82f6;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #3b82f6;
                border-color: #2563eb;
            }
            QCheckBox {
                spacing: 8px;
                color: #e2e8f0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #475569;
            }
            QCheckBox::indicator:checked {
                background-color: #3b82f6;
                border-color: #2563eb;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar {
                background-color: #1e293b;
                border-radius: 4px;
                width: 12px;
            }
            QScrollBar::handle {
                background-color: #475569;
                border-radius: 4px;
            }
            QScrollBar::handle:hover {
                background-color: #60a5fa;
            }
        """)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #121212;")
        control_widget = QWidget()
        control_widget.setObjectName("control_widget")
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
        self.volt_div_spinbox.setRange(1e-3, 1e3)  # 1mV to 1000V
        self.volt_div_spinbox.setValue(1.0)  # Default 1V/div
        self.volt_div_spinbox.setDecimals(3)  # Allow millivolt precision
        self.volt_div_spinbox.setSingleStep(1e-3)  # Millivolt steps
        self.volt_div_spinbox.setStepType(QDoubleSpinBox.StepType.AdaptiveDecimalStepType)
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
        vertical_group.setLayout(vertical_layout)
        self.main_layout.addWidget(vertical_group)

        # Horizontal Controls
        horizontal_group = QGroupBox("Horizontal Controls")
        horizontal_layout = QFormLayout()
        self.time_div_spinbox = QDoubleSpinBox()
        self.time_div_spinbox.setRange(1e-9, 1e6)  # 1ns to 1000000s (10^6)
        self.time_div_spinbox.setValue(1.0)  # Default 1s/div
        self.time_div_spinbox.setDecimals(9)  # Allow nanosecond precision
        self.time_div_spinbox.setSingleStep(1e-9)  # Nanosecond steps
        self.time_div_spinbox.setStepType(QDoubleSpinBox.StepType.AdaptiveDecimalStepType)
        horizontal_layout.addRow("Time/Div (s):", self.time_div_spinbox)
        self.horiz_pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.horiz_pos_slider.setRange(-50, 50)  # ±5 divisions * 10 for finer control
        self.horiz_pos_slider.setValue(0)
        self.horiz_pos_slider.valueChanged.connect(self.update_horizontal_position)
        horizontal_layout.addRow("Position:", self.horiz_pos_slider)
        horizontal_group.setLayout(horizontal_layout)
        self.main_layout.addWidget(horizontal_group)  # Changed to self.main_layout
        # Trigger Controls
        trigger_group = QGroupBox("Trigger Controls")
        trigger_layout = QFormLayout()
        self.trigger_spinbox = QDoubleSpinBox()
        self.trigger_spinbox.setRange(-5000, 5000)  # Allow negative values
        self.trigger_spinbox.setValue(0)  # Standard default is 0V
        trigger_layout.addRow("Trigger Level:", self.trigger_spinbox)
        
        self.trigger_mode_combo = QComboBox()
        self.trigger_mode_combo.addItems(["Auto", "Normal", "Single"])
        self.trigger_mode_combo.setCurrentText("Auto")  # Auto is standard default
        trigger_layout.addRow("Mode:", self.trigger_mode_combo)
        
        self.trigger_source_combo = QComboBox()
        self.trigger_source_combo.addItems(["CH1", "CH2", "CH3", "CH4", "External"])
        self.trigger_source_combo.setCurrentText("CH1")  # CH1 is standard default
        trigger_layout.addRow("Source:", self.trigger_source_combo)
        
        self.trigger_slope_combo = QComboBox()
        self.trigger_slope_combo.addItems(["Rising", "Falling"])
        self.trigger_slope_combo.setCurrentText("Rising")  # Rising is standard default
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
        self.probe_attenuation_combo.currentIndexChanged.connect(self.update_probe_attenuation)
        input_layout.addRow("Probe Attenuation:", self.probe_attenuation_combo)
        self.impedance_combo = QComboBox()
        self.impedance_combo.addItems(["1 MΩ", "50 Ω"])
        self.impedance_combo.currentIndexChanged.connect(self.update_impedance)
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
        self.record_button = QPushButton("Record Waveform")
        self.record_button.setStyleSheet("background-color: #90bf43; color: white; padding: 10px;")
        self.record_button.clicked.connect(self.record_data)
        utility_layout.addWidget(self.record_button)
        utility_group.setLayout(utility_layout)
        self.main_layout.addWidget(utility_group)

        # Channel Controls
        channel_controls_layout = QHBoxLayout()
        self.channel_checkboxes = []
        for i in range(4):
            checkbox = QCheckBox(f"CH{i+1}")
            checkbox.setChecked(i == 0)  # Only check Channel 1
            if i == 0:  # Only enable Channel 1 checkbox
                checkbox.stateChanged.connect(lambda state, idx=i: self.toggle_channel(idx, state))
            else:
                checkbox.setEnabled(False)  # Disable other channels
            checkbox.setStyleSheet(f"color: {colors[i]};")
            self.channel_checkboxes.append(checkbox)
            channel_controls_layout.addWidget(checkbox)
        self.main_layout.addLayout(channel_controls_layout)

        # Add after other control groups
        coupling_group = QGroupBox("Channel Coupling")
        coupling_layout = QGridLayout()
        self.coupling_combos = []

        for i in range(4):
            label = QLabel(f"CH{i+1} Coupling:")
            combo = QComboBox()
            combo.addItems(["DC", "AC", "GND"])  # DC first as it's standard default
            combo.setCurrentText("DC")  # Set DC as default
            combo.currentTextChanged.connect(lambda mode, ch=i: self.update_channel_coupling(ch, mode))
            self.coupling_combos.append(combo)
            coupling_layout.addWidget(label, i, 0)
            coupling_layout.addWidget(combo, i, 1)
            
        coupling_group.setLayout(coupling_layout)
        control_layout.addWidget(coupling_group)

        control_layout.addStretch()  # Push controls to top
        scroll.setWidget(control_widget)
        main_layout.addWidget(scroll)

    def toggle_channel(self, channel_idx, state):
        if channel_idx == 0:  # Only allow Channel 1 to be toggled
            self.channel_active[channel_idx] = bool(state)
            self.update_plot()

    def populate_com_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.com_port_selector.clear()
        self.com_port_selector.addItems(ports if ports else ["No Ports Found"])

    def update_plot(self):
        if self.plot_window:
            time_div = self.time_div_spinbox.value()
            voltage_div = self.volt_div_spinbox.value()
            trigger_level = self.trigger_spinbox.value() / 1000
            trigger_source = self.trigger_source_combo.currentIndex()
            trigger_slope = self.trigger_slope_combo.currentText()
            trigger_mode = self.trigger_mode_combo.currentText()

            # Check trigger condition
            triggered = False
            if trigger_mode != "Auto":  # Only check trigger for Normal and Single modes
                if self.data_buffer[trigger_source] and len(self.data_buffer[trigger_source]) >= 2:
                    for i in range(max(0, len(self.data_buffer[trigger_source]) - 100), 
                                 len(self.data_buffer[trigger_source]) - 1):
                        prev_val = self.data_buffer[trigger_source][i]
                        curr_val = self.data_buffer[trigger_source][i + 1]
                        
                        if ((trigger_slope == "Rising" and 
                             prev_val < trigger_level <= curr_val) or 
                            (trigger_slope == "Falling" and 
                             prev_val > trigger_level >= curr_val)):
                            triggered = True
                            break

            if trigger_mode == "Normal" and not triggered:
                return
            elif trigger_mode == "Single" and triggered:
                self.stop_acquisition()

            self.plot_window.update_plot(
                self.data_buffer,
                self.channel_active,
                time_div,
                voltage_div,
                self.display_window,
                self.sample_rate,
                self.channel_positions,
                self.horizontal_position,
                self.probe_attenuation
            )

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
            self.serial_thread = SerialReader(
                channels=4,
                impedance=self.impedance
            )
            
            # Set initial coupling modes
            for channel, combo in enumerate(self.coupling_combos):
                mode = combo.currentText()
                self.serial_thread.set_channel_coupling(channel, mode)
                
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
        # Process single data point
        for i in range(len(self.data_buffer)):
            if i < len(data):
                self.data_buffer[i].append(data[i])
                while len(self.data_buffer[i]) > self.max_samples:
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
        
        filename, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Snapshot", 
            "", 
            "PNG Files (*.png);;JPG Files (*.jpg);;All Files (*)"
        )
        print(f"Selected filename: {filename}")
        
        if filename:
            try:
                if not (filename.endswith('.png') or filename.endswith('.jpg')):
                    filename += '.png'
                    
                # Create exporter using ImageExporter directly
                exporter = ImageExporter(self.plot_window.plot_widget.plotItem)
                # Set resolution
                exporter.params.param('width').setValue(1200)
                exporter.params.param('height').setValue(800)
                # Set antialias
                exporter.params.param('antialias').setValue(True)
                # Export
                exporter.export(filename)
                print(f"Snapshot saved to {filename}")
                
            except Exception as e:
                print(f"Error saving snapshot: {e}")
                QMessageBox.critical(self, "Error", f"Could not save snapshot: {str(e)}")

    def update_coupling(self, text):
        print(f"Coupling set to {text} for {self.channel_selector.currentText()}")

    def update_vertical_position(self, value):
        channel = self.channel_selector.currentIndex()
        self.channel_positions[channel] = value
        self.update_plot()

    def update_horizontal_position(self, value):
        self.horizontal_position = value / 10.0  # Convert slider value to divisions
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
        self.trigger_spinbox.setValue(0)  # 0V is standard default
        self.trigger_mode_combo.setCurrentText("Auto")
        self.trigger_source_combo.setCurrentText("CH1")
        self.trigger_slope_combo.setCurrentText("Rising")
        self.trigger_holdoff_spinbox.setValue(0)
        self.pos_slider.setValue(0)
        self.horiz_pos_slider.setValue(0)
        # Set all channels to DC coupling
        for combo in self.coupling_combos:
            combo.setCurrentText("DC")
        # Only enable Channel 1
        self.channel_active = [True, False, False, False]
        for i, checkbox in enumerate(self.channel_checkboxes):
            checkbox.setChecked(i == 0)
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

    def update_impedance(self, index):
        impedance_str = self.impedance_combo.currentText()
        if impedance_str == "1 MΩ":
            self.impedance = 1e6
        elif impedance_str == "50 Ω":
            self.impedance = 50.0

        if self.serial_thread:
            self.serial_thread.set_impedance(self.impedance)

        self.update_data()
        self.update_plot()

    def update_probe_attenuation(self, index):
        attenuation_str = self.probe_attenuation_combo.currentText()
        if attenuation_str == "1x":
            self.probe_attenuation = 1.0
        elif attenuation_str == "10x":
            self.probe_attenuation = 10.0

        self.update_data()
        self.update_plot()

    def update_data(self):
        # Apply probe attenuation to the data buffer
        for i in range(len(self.data_buffer)):
            if self.channel_active[i]:
                self.data_buffer[i] = [value / self.probe_attenuation for value in self.data_buffer[i]]


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = OscilloscopeApp()
    window.show()
    sys.exit(app.exec())