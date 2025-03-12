import sys
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

    def __init__(self, channels=4, ch1_amplitude=2.5, mode='AC', impedance=1e6):
        super().__init__()
        self.channels = channels
        self.running = False  # Initialize as False
        self.sample_rate = 200
        self.time_step = 0.0
        self.ch1_amplitude = ch1_amplitude
        self.mode = mode
        self.impedance = impedance
        self.coupling_modes = ['AC'] * channels

    def run(self):
        self.running = True
        while self.running:
            dummy_data = []
            # Generate CH1 data with larger amplitude
            if self.mode == 'AC':
                ch1_value = self.ch1_amplitude * np.sin(2 * np.pi * 1 * self.time_step)  # Changed to 1 Hz for clearer peaks
            elif self.mode == 'DC':
                ch1_value = self.ch1_amplitude * np.abs(np.sin(2 * np.pi * 1 * self.time_step))

            # Apply impedance effect
            if self.impedance < 1e6:
                attenuation_factor = self.impedance / 1e6
                ch1_value *= attenuation_factor

            # Apply coupling mode to CH1
            if self.coupling_modes[0] == 'AC':
                ch1_value -= np.mean([ch1_value])
            elif self.coupling_modes[0] == 'GND':
                ch1_value = 0.0

            dummy_data.append(ch1_value)

            # Generate other channels with smaller amplitudes
            for i in range(1, self.channels):
                value = 0.5 * np.sin(2 * np.pi * 0.5 * self.time_step + (i * np.pi/2))
                if self.coupling_modes[i] == 'AC':
                    value -= np.mean([value])
                elif self.coupling_modes[i] == 'GND':
                    value = 0.0
                dummy_data.append(value)

            self.data_received.emit(dummy_data)
            self.time_step += 1.0 / self.sample_rate
            time.sleep(1.0 / self.sample_rate)

    def stop(self):
        self.running = False
        self.quit()
        self.wait()

    def set_ch1_amplitude(self, amplitude):
        self.ch1_amplitude = amplitude

    def set_mode(self, mode):
        self.mode = mode

    def set_impedance(self, impedance):
        self.impedance = impedance

    def set_coupling(self, channel, mode):
        self.coupling_modes[channel] = mode

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

    def update_plot(self, data_buffer, channel_active, time_div, voltage_div, display_window, sample_rate, channel_positions, horizontal_position, probe_attenuation):
        sample_duration_ms = 1000 / sample_rate  
        display_window_ms = time_div * 100

        for i, trace in enumerate(self.traces):
            if channel_active[i] and data_buffer[i]:
                num_points = min(len(data_buffer[i]), display_window)
                x_values = np.linspace(0, display_window_ms, num_points)
                # Scale the y-values properly
                y_values = np.array(data_buffer[i][-num_points:]) + channel_positions[i]
                trace.setData(x_values, y_values)
            else:
                trace.setData([], [])

        self.plot_widget.setXRange(0, display_window_ms)
        self.plot_widget.setYRange(-5, 5)  # Set fixed Y range for better visibility

class OscilloscopeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Oscilloscope")
        self.setGeometry(100, 100, 1200, 800)
        self.data_buffer = [[] for _ in range(4)]
        self.max_samples = 1000    # Increased to match display_window
        self.display_window = 1000  # Increased for better visibility
        self.sample_rate = 200
        self.serial_thread = None
        self.channel_active = [True, True, True, True]
        self.channel_positions = [0, 0, 0, 0]
        self.horizontal_position = 0
        self.is_running = False
        self.plot_window = None
        self.ch1_amplitude = 2.5  # Default amplitude
        self.probe_attenuation = 1.0  # Default to 1x attenuation
        self.impedance = 1e6  # Default to 1 MΩ impedance
        self.coupling_modes = ['AC', 'AC', 'AC', 'AC']  # Default coupling modes
        self.initUI()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)

    def initUI(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #555;
                border-radius: 5px;
                margin-top: 1ex;
                padding: 10px;
                font-weight: bold;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QLabel {
                color: #ffffff;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #2c2c2c;
                color: #ffffff;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px;
            }
            QComboBox::drop-down {
                border: 0px;
                width: 20px;
                background-color: #2c2c2c;
            }
            QComboBox::down-arrow {
                image: url(:/qt-project.org/styles/commonstyle/images/downarrow-ffffff-20.png);
            }
            QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #2c2c2c;
                border: 1px solid #555;
                width: 16px;
            }
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
            QCheckBox {
                color: #ffffff;
            }
            QPushButton {
                padding: 10px;
                border-radius: 3px;
                color: #ffffff;
            }
            QPushButton#start_button { background-color: #1E88E5; }
            QPushButton#stop_button { background-color: #D32F2F; }
            QPushButton#run_button { background-color: #FF9800; }
            QPushButton#auto_set_button { background-color: #FF5722; }
            QPushButton#default_button { background-color: #9E9E9E; }
            QPushButton#save_button { background-color: #388E3C; }
            QPushButton#record_button { background-color: #90bf43; }
            QTabWidget {
                background-color: #121212;
            }
            QTabBar::tab {
                background-color: #2c2c2c;
                color: #ffffff;
                padding: 10px;
                margin-right: 2px;
                border: 1px solid #555;
                border-bottom: none;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
            }
            QTabBar::tab:selected {
                background-color: #1E88E5;
                color: #ffffff;
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
        control_layout.addWidget(vertical_group)

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
        control_layout.addWidget(horizontal_group)

        trigger_group = QGroupBox("Trigger Controls")
        trigger_layout = QFormLayout()
        self.trigger_spinbox = QDoubleSpinBox()
        self.trigger_spinbox.setRange(0, 5000)
        self.trigger_spinbox.setValue(2000)
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
        utility_layout.addWidget(self.record_button)
        utility_group.setLayout(utility_layout)
        control_layout.addWidget(utility_group)

        channel_controls_layout = QHBoxLayout()
        self.channel_checkboxes = []
        for i in range(4):
            checkbox = QCheckBox(f"CH{i+1}")
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(lambda state, idx=i: self.toggle_channel(idx, state))
            checkbox.setStyleSheet(f"color: {colors[i]};")
            self.channel_checkboxes.append(checkbox)
            channel_controls_layout.addWidget(checkbox)
        control_layout.addLayout(channel_controls_layout)

        ch1_amplitude_layout = QHBoxLayout()
        ch1_amplitude_label = QLabel("CH1 Amplitude (V):")
        ch1_amplitude_layout.addWidget(ch1_amplitude_label)
        self.ch1_amplitude_spinbox = QDoubleSpinBox()
        self.ch1_amplitude_spinbox.setRange(0.1, 10.0)
        self.ch1_amplitude_spinbox.setValue(2.5)
        self.ch1_amplitude_spinbox.setSingleStep(0.1)
        self.ch1_amplitude_spinbox.valueChanged.connect(self.update_ch1_amplitude)
        ch1_amplitude_layout.addWidget(self.ch1_amplitude_spinbox)
        control_layout.addLayout(ch1_amplitude_layout)

        # Add mode selection
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Mode:")
        mode_layout.addWidget(mode_label)
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["AC", "DC"])
        self.mode_selector.currentTextChanged.connect(self.update_mode)
        mode_layout.addWidget(self.mode_selector)
        control_layout.addLayout(mode_layout)

        # Creates coupling controls for each channel
        self.coupling_combos = []
        for i in range(4):
            coupling_combo = QComboBox()
            coupling_combo.addItems(["AC", "DC", "GND"])
            coupling_combo.setCurrentText("AC")
            coupling_combo.currentIndexChanged.connect(
                lambda index, channel=i: self.update_coupling(channel, coupling_combo.currentText())
            )
            self.coupling_combos.append(coupling_combo)

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
        pass

    def calculate_frequency(self, data):
        if len(data) < 2:
            print("Not enough data points to calculate frequency.")
            return None

        data = np.array(data)  # Convert data to a NumPy array

        # Detect if the waveform is pulsating DC (full-wave rectified) or AC
        if np.all(data >= 0):
            # Full-wave rectified (pulsating DC)
            peaks = np.where((data[1:-1] > data[:-2]) & (data[1:-1] > data[2:]))[0] + 1
            print(f"Peaks: {peaks}")
            if len(peaks) < 2:
                print("Not enough peaks to calculate frequency.")
                return None
            period_samples = np.diff(peaks)
        else:
            # AC waveform
            zero_crossings = np.where(np.diff(np.sign(data)))[0]
            print(f"Zero crossings: {zero_crossings}")
            if len(zero_crossings) < 2:
                print("Not enough zero crossings to calculate frequency.")
                return None
            period_samples = np.diff(zero_crossings)

        print(f"Period samples: {period_samples}")
        avg_period_samples = np.mean(period_samples)
        print(f"Average period in samples: {avg_period_samples}")
        frequency = self.sample_rate / avg_period_samples
        print(f"Calculated frequency: {frequency}")
        return frequency

    def calculate_rms(self, data):
        return np.sqrt(np.mean(np.square(data)))

    def default_setup(self):
        self.time_div_spinbox.setValue(1)
        self.volt_div_spinbox.setValue(1)
        self.trigger_spinbox.setValue(2000)
        self.trigger_mode_combo.setCurrentText("Normal")
        self.trigger_source_combo.setCurrentText("CH1")
        self.trigger_slope_combo.setCurrentText("Rising")
        self.trigger_holdoff_spinbox.setValue(0)
        self.pos_slider.setValue(0)
        self.horiz_pos_slider.setValue(0)
        self.channel_active = [True, True, True, True]
        for checkbox in self.channel_checkboxes:
            checkbox.setChecked(True)
        if self.plot_window:
            self.update_plot()

    def update_plot(self):
        if self.plot_window:
            time_div = self.time_div_spinbox.value()
            voltage_div = self.volt_div_spinbox.value()
            trigger_level = self.trigger_spinbox.value()  # Remove division by 1000
            trigger_source = self.trigger_source_combo.currentIndex()
            trigger_slope = self.trigger_slope_combo.currentText()
            trigger_mode = self.trigger_mode_combo.currentText()

            # Only check trigger in Normal mode
            if trigger_mode == "Normal":
                triggered = False
                if self.is_running:
                    for i, buffer in enumerate(self.data_buffer):
                        if i == trigger_source and len(buffer) > 1 and self.channel_active[i]:
                            last_val = buffer[-2]
                            curr_val = buffer[-1]
                            if (trigger_slope == "Rising" and last_val < trigger_level <= curr_val) or \
                               (trigger_slope == "Falling" and last_val > trigger_level >= curr_val):
                                triggered = True
                                break
                    
                    if not triggered:
                        return

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

            # Calculate and update frequency and RMS voltage
            if self.channel_active[0] and self.data_buffer[0]:
                # Apply probe attenuation to the data
                attenuated_data = [value / self.probe_attenuation for value in self.data_buffer[0]]
                frequency = self.calculate_frequency(attenuated_data)
                rms_voltage = self.calculate_rms(attenuated_data)
                self.measure_freq.setText(f"Frequency: {frequency:.2f} Hz" if frequency else "Frequency: N/A")
                self.measure_rms.setText(f"RMS Voltage: {rms_voltage:.2f} V")
            else:
                self.measure_freq.setText("Frequency: N/A")
                self.measure_rms.setText("RMS Voltage: N/A")

    def start_acquisition(self):
        if not self.serial_thread:
            mode = self.mode_selector.currentText()
            self.serial_thread = SerialReader(
                channels=4, 
                ch1_amplitude=self.ch1_amplitude, 
                mode=mode, 
                impedance=self.impedance
            )
            # Set initial coupling modes
            for i, mode in enumerate(self.coupling_modes):
                self.serial_thread.set_coupling(i, mode)
            
            # Clear existing data buffers
            self.data_buffer = [[] for _ in range(4)]
            
            self.serial_thread.data_received.connect(self.process_data)
            self.serial_thread.start()
            self.is_running = True
            
            if not self.plot_window:
                self.plot_window = PlotWindow(self)
                self.plot_window.show()
            
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
        # Ensure data is being received
        if not data:
            return
            
        for i in range(min(len(data), len(self.data_buffer))):
            self.data_buffer[i].append(data[i])
            # Keep buffer size limited
            while len(self.data_buffer[i]) > self.max_samples:
                self.data_buffer[i].pop(0)
                
        if self.is_running and self.plot_window:
            self.update_plot()

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
        filename, _ = QFileDialog.getSaveFileName(self, "Save Snapshot", "", "PNG Files (*.png);;JPG Files (*.jpg);;All Files (*)")
        if filename:
            try:
                if not (filename.endswith('.png') or filename.endswith('.jpg')):
                    filename += '.png'
                if self.plot_window:
                    exporter = pg.exporters.ImageExporter(self.plot_window.plot_widget.plotItem)
                else:
                    plot_widget = pg.PlotWidget()
                    plot_widget.setTitle("Oscilloscope Signal")
                    plot_widget.setLabel('left', 'Voltage', 'V')
                    plot_widget.setLabel('bottom', 'Time', 'ms')
                    plot_widget.showGrid(x=True, y=True, alpha=0.3)
                    plot_widget.setBackground('#000A1E')
                    colors = ['#FF0000', '#00FF00', '#33CCFF', '#FFFF00']
                    traces = [plot_widget.plot([], [], pen=pg.mkPen(color=color, width=2)) for color in colors]
                    for i, trace in enumerate(traces):
                        if self.channel_active[i] and self.data_buffer[i]:
                            num_points = min(len(self.data_buffer[i]), self.display_window)
                            x_values = np.linspace(0, num_points * (1000 / self.sample_rate) / (self.time_div_spinbox.value() * 10), num_points)
                            y_values = np.array(self.data_buffer[i][-num_points:]) * self.volt_div_spinbox.value()
                            trace.setData(x_values, y_values)
                    exporter = pg.exporters.ImageExporter(plot_widget.plotItem)
                exporter.parameters()['width'] = 900
                exporter.export(filename)
            except PermissionError:
                pass
            except Exception:
                pass

    def update_coupling(self, channel, mode):
        self.coupling_modes[channel] = mode
        if self.serial_thread:
            self.serial_thread.set_coupling(channel, mode)
        if self.plot_window:
            self.update_plot()

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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = OscilloscopeApp()
    window.show()
    sys.exit(app.exec())