import sys
import numpy as np
import pandas as pd
import pyqtgraph as pg
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QComboBox, QSpinBox, QTabWidget, QFileDialog, QHBoxLayout, QCheckBox,
    QDoubleSpinBox, QSlider, QGroupBox, QFormLayout, QScrollArea, QGridLayout  # Add QGridLayout here
)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QColor
from pyqtgraph.exporters import ImageExporter

class SerialReader(QThread):
    data_received = pyqtSignal(list)

    def __init__(self, channels=4, ch1_amplitude=2.5, impedance=1e6):
        super().__init__()
        self.channels = channels
        self.running = False
        self.sample_rate = 200
        self.time_step = 0.0
        self.ch1_amplitude = ch1_amplitude
        self.impedance = impedance
        # Separate buffer and coupling mode for each channel
        self.signal_buffers = [[] for _ in range(channels)]
        self.coupling_modes = ['AC'] * channels  # Default AC coupling for all channels
        self.frequency = 5

    def run(self):
        self.running = True
        while self.running:
            dummy_data = []

            # Generate and process each channel
            for channel in range(self.channels):
                # Generate signal (different for each channel)
                if channel == 0:  # CH1
                    base_signal = np.abs(np.sin(2 * np.pi * self.frequency * self.time_step))
                else:  # Other channels
                    base_signal = np.sin(2 * np.pi * (self.frequency/(channel+1)) * self.time_step)

                # Apply coupling mode for this channel
                if self.coupling_modes[channel] == 'AC':
                    self.signal_buffers[channel].append(base_signal)
                    if len(self.signal_buffers[channel]) > 100:
                        self.signal_buffers[channel].pop(0)
                    dc_offset = np.mean(self.signal_buffers[channel])
                    channel_value = base_signal - dc_offset
                    
                elif self.coupling_modes[channel] == 'DC':
                    channel_value = base_signal
                    
                elif self.coupling_modes[channel] == 'GND':
                    channel_value = 0.0

                # Apply amplitude and impedance (for CH1 only)
                if channel == 0:
                    channel_value *= self.ch1_amplitude
                if self.impedance < 1e6:
                    channel_value *= (self.impedance / 1e6)

                dummy_data.append(channel_value)

            self.data_received.emit(dummy_data)
            self.time_step += 1.0 / self.sample_rate
            time.sleep(1.0 / self.sample_rate)

    def stop(self):
        self.running = False
        self.quit()
        self.wait()

    def set_ch1_amplitude(self, amplitude):
        self.ch1_amplitude = amplitude

    def set_channel_coupling(self, channel, mode):
        """Set coupling mode for a specific channel"""
        if 0 <= channel < self.channels:
            self.coupling_modes[channel] = mode
            self.signal_buffers[channel].clear()

    def set_impedance(self, impedance):
        self.impedance = impedance

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
        # Calculate time base with microsecond precision
        sample_duration_us = 1000000.0 / sample_rate  # Convert to microseconds
        total_div = 10  # Standard oscilloscope has 10 divisions
        display_window_time = time_div * total_div  # Total time window
        
        for i, trace in enumerate(self.traces):
            if channel_active[i] and data_buffer[i]:
                num_points = min(len(data_buffer[i]), display_window)
                
                # Generate time values (x-axis) with microsecond precision
                x_values = np.linspace(
                    horizontal_position * time_div * 1000000,  # Convert to microseconds
                    (horizontal_position * time_div + display_window_time) * 1000000,
                    num_points
                ) / 1000000.0  # Convert back to seconds for display
                
                # Scale voltage values (y-axis)
                y_values = np.array(data_buffer[i][-num_points:])
                y_values = y_values / probe_attenuation
                y_values = y_values + (channel_positions[i] / 100.0 * 8 * voltage_div)
                
                trace.setData(x_values, y_values)
            else:
                trace.setData([], [])

        # Set view ranges with microsecond precision
        self.plot_widget.setXRange(
            horizontal_position * time_div,
            horizontal_position * time_div + display_window_time
        )
        self.plot_widget.setYRange(-4 * voltage_div, 4 * voltage_div)

class OscilloscopeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Oscilloscope")
        self.setGeometry(100, 100, 1200, 800)
        self.data_buffer = [[] for _ in range(4)]
        self.max_samples = 500  # Increased to accommodate more samples
        self.display_window = 500  # Increased from 100 to 500 for better resolution
        self.sample_rate = 100  # Match the SerialReader sample rate
        self.serial_thread = None
        self.channel_active = [True, False, False, False]  # Only CH1 active by default
        self.channel_positions = [0, 0, 0, 0]
        self.horizontal_position = 0
        self.is_running = False
        self.plot_window = None
        self.ch1_amplitude = 2.5  # Default amplitude
        self.probe_attenuation = 1.0  # Default to 1x attenuation
        self.impedance = 1e6  # Default to 1 MΩ impedance
        self.coupling_modes = ['DC'] * 4  # Default to DC coupling
        self.trigger_level = 0  # Default 0V trigger
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
        control_layout = QVBoxLayout(control_widget)
        control_layout.setSpacing(15)

        colors = ['#FF0000', '#00FF00', '#33CCFF', '#FFFF00']

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
        self.baud_selector.setRange(9600, 115200)
        self.baud_selector.setValue(115200)
        connectivity_layout.addWidget(self.baud_selector)
        connectivity_group.setLayout(connectivity_layout)
        control_layout.addWidget(connectivity_group)

        display_group = QGroupBox("Display Controls")
        display_layout = QFormLayout()
        self.intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self.intensity_slider.setRange(10, 100)
        self.intensity_slider.setValue(100)
        self.intensity_slider.setStyleSheet("""
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
        self.intensity_slider.valueChanged.connect(self.update_intensity)
        display_layout.addRow("Intensity:", self.intensity_slider)
        self.grid_check = QCheckBox("Grid")
        self.grid_check.setChecked(True)
        self.grid_check.stateChanged.connect(self.toggle_grid)
        display_layout.addRow(self.grid_check)
        display_group.setLayout(display_layout)
        control_layout.addWidget(display_group)

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
        control_layout.addWidget(vertical_group)

        horizontal_group = QGroupBox("Horizontal Controls")
        horizontal_layout = QFormLayout()

        # Add channel selector for time division
        self.channel_time_div_selector = QComboBox()
        self.channel_time_div_selector.addItems([f"CH{i + 1}" for i in range(4)])
        horizontal_layout.addRow("Channel:", self.channel_time_div_selector)

        # Existing time division control
        self.time_div_spinbox = QDoubleSpinBox()
        self.time_div_spinbox.setRange(1e-9, 1e6)  # 1ns to 1000000s
        self.time_div_spinbox.setValue(1.0)  # Default 1ms/div
        self.time_div_spinbox.setDecimals(9)  # Allow nanosecond precision
        self.time_div_spinbox.setSingleStep(1e-9)  # Nanosecond steps
        self.time_div_spinbox.setStepType(QDoubleSpinBox.StepType.AdaptiveDecimalStepType)
        self.time_div_spinbox.valueChanged.connect(self.update_selected_channel_time_div)
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
        control_layout.addWidget(horizontal_group)

        trigger_group = QGroupBox("Trigger Controls")
        trigger_layout = QFormLayout()
        self.trigger_spinbox = QDoubleSpinBox()
        self.trigger_spinbox.setRange(-5000, 5000)  # Allow negative values
        self.trigger_spinbox.setValue(0)  # Default 0V
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
        control_layout.addWidget(trigger_group)

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
        control_layout.addWidget(input_group)

        measure_group = QGroupBox("Measurements")
        measure_layout = QVBoxLayout()
        self.measure_freq = QLabel("Frequency: N/A")
        measure_layout.addWidget(self.measure_freq)
        self.measure_rms = QLabel("RMS Voltage: N/A")
        measure_layout.addWidget(self.measure_rms)
        measure_group.setLayout(measure_layout)
        control_layout.addWidget(measure_group)

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
        utility_group.setLayout(utility_layout)
        control_layout.addWidget(utility_group)

        # Update the channel controls section
        channel_controls_layout = QHBoxLayout()
        self.channel_checkboxes = []
        for i in range(4):
            checkbox = QCheckBox(f"CH{i+1}")
            checkbox.setChecked(i == 0)  # Only check CH1 (index 0)
            if i == 0:  # Only enable CH1 checkbox
                checkbox.stateChanged.connect(lambda state, idx=i: self.toggle_channel(idx, state))
            else:
                checkbox.setEnabled(False)  # Disable other channels
            checkbox.setStyleSheet(f"color: {colors[i]};")
            self.channel_checkboxes.append(checkbox)
            channel_controls_layout.addWidget(checkbox)
        control_layout.addLayout(channel_controls_layout)

        ch1_amplitude_layout = QHBoxLayout()
        ch1_amplitude_label = QLabel("CH1 Amplitude (V):")
        ch1_amplitude_layout.addWidget(ch1_amplitude_label)
        self.ch1_amplitude_spinbox = QDoubleSpinBox()
        self.ch1_amplitude_spinbox.setRange(0.001, 1000.0)  # Changed from 0.1-10V to 1mV-1000V
        self.ch1_amplitude_spinbox.setValue(2.5)  # Default stays at 2.5V
        self.ch1_amplitude_spinbox.setDecimals(3)  # Allow millivolt precision
        self.ch1_amplitude_spinbox.setSingleStep(0.001)  # 1mV steps
        self.ch1_amplitude_spinbox.setStepType(QDoubleSpinBox.StepType.AdaptiveDecimalStepType)
        self.ch1_amplitude_spinbox.valueChanged.connect(self.update_ch1_amplitude)
        ch1_amplitude_layout.addWidget(self.ch1_amplitude_spinbox)
        control_layout.addLayout(ch1_amplitude_layout)

        # Replace the single mode selector with per-channel coupling controls
        coupling_group = QGroupBox("Channel Coupling")
        coupling_layout = QGridLayout()
        self.coupling_combos = []
        
        # Initialize coupling combos with DC default
        for i in range(4):
            label = QLabel(f"CH{i+1} Coupling:")
            combo = QComboBox()
            combo.addItems(["DC", "AC", "GND"])  # Make DC first option
            combo.setCurrentText("DC")  # Set DC as default
            combo.currentTextChanged.connect(lambda mode, ch=i: self.update_channel_coupling(ch, mode))
            self.coupling_combos.append(combo)
            coupling_layout.addWidget(label, i, 0)
            coupling_layout.addWidget(combo, i, 1)
            
        coupling_group.setLayout(coupling_layout)
        control_layout.addWidget(coupling_group)

        control_layout.addStretch()
        scroll.setWidget(control_widget)
        main_layout.addWidget(scroll)

    def update_intensity(self, value):
        alpha = value / 100.0
        if self.plot_window:
            for trace in self.plot_window.traces:
                color = QColor(trace.opts['pen'].color())
                color.setAlphaF(alpha)
                trace.setPen(pg.mkPen(color=color, width=2))
        self.update_plot()

    def toggle_grid(self, state):
        if self.plot_window:
            self.plot_window.plot_widget.showGrid(x=state, y=state, alpha=0.3)

    def toggle_channel(self, channel_idx, state):
        self.channel_active[channel_idx] = bool(state)
        if self.plot_window:
            self.update_plot()

    def update_ch1_amplitude(self, value):
        self.ch1_amplitude = value
        if self.serial_thread:
            self.serial_thread.set_ch1_amplitude(value)
        if self.plot_window:
            self.update_plot()

    def populate_com_ports(self):
        self.com_port_selector.addItems(["COM1", "COM2", "COM3", "COM4", "COM5"])

    def update_vertical_position(self, value):
        channel = self.channel_selector.currentIndex()
        self.channel_positions[channel] = value
        if self.plot_window:
            self.update_plot()

    def update_horizontal_position(self, value):
        self.horizontal_position = value
        if self.plot_window:
            self.update_plot()

    def update_trigger_mode(self, mode):
        if mode == "Single" and self.is_running and self.plot_window:
            self.timer.stop()
        elif mode in ["Auto", "Normal"] and self.plot_window:
            self.timer.start(50)

    def run_plot(self):
        if not self.plot_window:
            self.plot_window = PlotWindow(self)
            self.plot_window.show()
            if self.is_running:
                self.timer.start(50)
            else:
                self.plot_window.update_plot(self.data_buffer, self.channel_active, 
                                            self.time_div_spinbox.value(), self.volt_div_spinbox.value(),
                                            self.display_window, self.sample_rate, 
                                            self.channel_positions, self.horizontal_position, self.probe_attenuation)

    def auto_set(self):
        """Automatically adjust settings to fit waveform on screen"""
        if not self.data_buffer[0]:  # If no data, return
            return

        # Get active channel data
        active_channel_data = None
        for i, data in enumerate(self.data_buffer):
            if self.channel_active[i] and data:
                active_channel_data = data
                break

        if active_channel_data is None:
            return

        # Calculate peak-to-peak voltage
        data_array = np.array(active_channel_data)
        min_voltage = np.min(data_array)
        max_voltage = np.max(data_array)
        vpp = max_voltage - min_voltage

        if vpp == 0:  # Avoid division by zero
            return

        # Set Volts/Div to fit waveform height (use 6 divisions)
        new_volts_div = vpp / 6
        self.volt_div_spinbox.setValue(max(0.1, min(new_volts_div, 10)))

        # Calculate and set Time/Div
        samples_per_division = len(active_channel_data) / 10  # Use 10 horizontal divisions
        time_per_sample = 1.0 / self.sample_rate
        new_time_div = samples_per_division * time_per_sample
        self.time_div_spinbox.setValue(max(0.1, min(new_time_div, 10)))

        # Center waveform vertically
        center = (max_voltage + min_voltage) / 2
        vertical_position = -center / self.volt_div_spinbox.value()
        self.pos_slider.setValue(int(max(-100, min(vertical_position * 100, 100))))

        # Reset horizontal position
        self.horiz_pos_slider.setValue(0)
        self.horizontal_position = 0

        # Set trigger level to 50% of Vpp
        trigger_level = min_voltage + (vpp / 2)
        self.trigger_spinbox.setValue(trigger_level * 1000)  # Convert to mV

        # Update the display
        self.update_plot()

    def calculate_frequency(self, data):
        if len(data) < 2:
            return None

        data = np.array(data)  # Convert data to a NumPy array

        # Detect if the waveform is pulsating DC (full-wave rectified) or AC
        if np.all(data >= 0):
            # Full-wave rectified (pulsating DC)
            peaks = np.where((data[1:-1] > data[:-2]) & (data[1:-1] > data[2:]))[0] + 1
            if len(peaks) < 2:
                return None
            period_samples = np.diff(peaks)
        else:
            # AC waveform
            zero_crossings = np.where(np.diff(np.sign(data)))[0]
            if len(zero_crossings) < 2:
                return None
            period_samples = np.diff(zero_crossings)

        avg_period_samples = np.mean(period_samples)
        frequency = self.sample_rate / avg_period_samples
        return frequency

    def calculate_rms(self, data):
        return np.sqrt(np.mean(np.square(data)))

    def default_setup(self):
        """Reset all settings to default oscilloscope values"""
        # Time and Voltage settings
        self.time_div_spinbox.setValue(1.0)      # 1 sec/div
        self.volt_div_spinbox.setValue(1.0)      # 1 V/div

        # Trigger settings
        self.trigger_spinbox.setValue(0)         # 0V trigger level
        self.trigger_mode_combo.setCurrentText("Auto")
        self.trigger_source_combo.setCurrentText("CH1")
        self.trigger_slope_combo.setCurrentText("Rising")
        self.trigger_holdoff_spinbox.setValue(0)

        # Position settings
        self.pos_slider.setValue(0)             # Center vertical position
        self.horiz_pos_slider.setValue(0)       # Center horizontal position
        self.horizontal_position = 0

        # Channel settings
        self.channel_active = [True, False, False, False]  # Only CH1 active
        for i, checkbox in enumerate(self.channel_checkboxes):
            checkbox.setChecked(i == 0)

        # Coupling settings
        for combo in self.coupling_combos:
            combo.setCurrentText("DC")          # Set DC coupling as default

        # Input settings
        self.probe_attenuation_combo.setCurrentText("1x")
        self.impedance_combo.setCurrentText("1 MΩ")

        # Update hardware settings if running
        if self.serial_thread:
            self.serial_thread.set_impedance(1e6)
            for channel in range(4):
                self.serial_thread.set_channel_coupling(channel, "DC")

        # Update display
        self.update_plot()

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
                    # Look for trigger in recent samples
                    for i in range(max(0, len(self.data_buffer[trigger_source]) - 100), 
                                 len(self.data_buffer[trigger_source]) - 1):
                        prev_val = self.data_buffer[trigger_source][i]
                        curr_val = self.data_buffer[trigger_source][i + 1]
                        
                        # Check for trigger condition
                        if ((trigger_slope == "Rising" and 
                             prev_val < trigger_level <= curr_val) or 
                            (trigger_slope == "Falling" and 
                             prev_val > trigger_level >= curr_val)):
                            triggered = True
                            break

            # Update display based on trigger mode
            if trigger_mode == "Normal" and not triggered:
                return  # Don't update if not triggered in Normal mode
            elif trigger_mode == "Single" and triggered:
                self.stop_acquisition()  # Stop after single trigger

            # Update the display
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

    def start_acquisition(self):
        if not self.serial_thread:
            # Initialize SerialReader without mode parameter
            self.serial_thread = SerialReader(
                channels=4, 
                ch1_amplitude=self.ch1_amplitude, 
                impedance=self.impedance
            )
            
            # Set initial coupling modes for all channels
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
                                        self.channel_positions, self.horizontal_position, self.probe_attenuation)

    def process_data(self, data):
        try:
            # Existing data buffer update code...
            for i in range(min(len(data), len(self.data_buffer))):
                self.data_buffer[i].append(data[i])
                if len(self.data_buffer[i]) > self.max_samples:
                    self.data_buffer[i].pop(0)

            # Calculate and update frequency and RMS for active channels
            for i, buffer in enumerate(self.data_buffer):
                if self.channel_active[i] and buffer:
                    # Frequency calculation
                    freq = self.calculate_frequency(buffer)
                    if freq is not None:
                        self.measure_freq.setText(f"Frequency: {freq:.2f} Hz")
                    else:
                        self.measure_freq.setText("Frequency: N/A")
                    
                    # RMS calculation
                    rms = self.calculate_rms(buffer)
                    self.measure_rms.setText(f"RMS Voltage: {rms:.3f} V")
                    break  # Only show first active channel's measurements

            # Update plot if running
            if self.is_running and self.plot_window:
                self.update_plot()

        except Exception as e:
            print(f"Error processing data: {e}")

    def change_time_division(self, delta):
        new_val = self.time_div_spinbox.value() + delta
        if 0.1 <= new_val <= self.time_div_spinbox.maximum():
            self.time_div_spinbox.setValue(new_val)
            if self.plot_window:
                self.update_plot()

    def change_voltage_division(self, delta):
        new_val = self.volt_div_spinbox.value() + delta
        if 0.1 <= new_val <= self.time_div_spinbox.maximum():
            self.time_div_spinbox.setValue(new_val)
            if self.plot_window:
                self.update_plot()

    def apply_trigger(self):
        if self.plot_window:
            self.update_plot()

    def save_data(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Snapshot", 
            "", 
            "PNG Files (*.png);;JPG Files (*.jpg);;All Files (*)"
        )
        if filename:
            try:
                if not (filename.endswith('.png') or filename.endswith('.jpg')):
                    filename += '.png'
                
                if self.plot_window:
                    exporter = ImageExporter(self.plot_window.plot_widget.plotItem)
                    exporter.params.param('width').setValue(1200)
                    exporter.params.param('height').setValue(800)
                    exporter.params.param('antialias').setValue(True)
                    exporter.export(filename)
                    print(f"Snapshot saved to {filename}")
                else:
                    print("No plot window available to save")
            except Exception as e:
                print(f"Error saving snapshot: {e}")
                QMessageBox.critical(self, "Error", f"Could not save snapshot: {str(e)}")

    def record_data(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Waveform Data", "", "CSV Files (*.csv);;All Files (*)")
        if filename:
            if not filename.endswith('.csv'):
                filename += '.csv'
            try:
                max_length = max(len(buffer) for buffer in self.data_buffer if buffer)
                if max_length == 0:
                    with open(filename, 'w') as file:
                        file.write("No data available\n")
                    return

                data_dict = {}
                for i, buffer in enumerate(self.data_buffer):
                    if self.channel_active[i]:
                        data_dict[f"Channel {i+1}"] = buffer + [0.0] * (max_length - len(buffer)) if buffer else [0.0] * max_length

                if not data_dict:
                    with open(filename, 'w') as file:
                        file.write("No active channels have data\n")
                    return

                df = pd.DataFrame(data_dict)
                df.to_csv(filename, index_label="Sample")
            except PermissionError:
                pass
            except Exception:
                pass

    def update_mode(self, mode):
        if self.serial_thread:
            self.serial_thread.set_mode(mode)

    def update_probe_attenuation(self, index):
        attenuation_str = self.probe_attenuation_combo.currentText()
        if attenuation_str == "1x":
            self.probe_attenuation = 1.0
        elif attenuation_str == "10x":
            self.probe_attenuation = 10.0
        # Apply changes to the data if necessary
        self.update_data()
        self.update_plot()

    def update_impedance(self, index):
        impedance_str = self.impedance_combo.currentText()
        if impedance_str == "1 MΩ":
            self.impedance = 1e6  # 1 MΩ in ohms
        elif impedance_str == "50 Ω":
            self.impedance = 50.0

        # Update the serial thread if it's running
        if self.serial_thread:
            self.serial_thread.set_impedance(self.impedance)

        # Apply changes to the displayed data
        self.update_data()
        self.update_plot()

    def update_data(self):
        # Implement any necessary data updates based on the new settings
        pass

    def update_channel_coupling(self, channel, mode):
        """Update coupling mode for a specific channel"""
        if self.serial_thread:
            self.serial_thread.set_channel_coupling(channel, mode)
            self.update_plot()

    def update_selected_channel_time_div(self, time_div):
        if self.plot_window:
            self.update_plot()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = OscilloscopeApp()
    window.show()
    sys.exit(app.exec())