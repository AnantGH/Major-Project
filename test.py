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

    def __init__(self, channels=4, impedance=1e6):
        super().__init__()
        self.channels = channels
        self.running = False
        self.impedance = impedance
        self.coupling_modes = ['DC'] * channels
        self.signal_buffers = [[] for _ in range(self.channels)]

        # Load data during initialization
        self.load_data()
        self.data_processed = False  # Flag to track whether data was processed

    def load_data(self):
        """Load data from the CSV file"""
        try:
            data = np.loadtxt('data1.csv', delimiter=',', dtype=float)
            print("Loading data from data1.csv...")
            
            # Verify data structure
            if data.ndim != 2 or data.shape[1] != 2:
                raise ValueError("Data file must have 2 columns (voltage and time)")
                
            self.signal = data[:, 0]  # First column (voltage)
            self.time = data[:, 1]    # Second column (time)
            print(f"Loaded {len(self.signal)} samples.")
            print(f"First few voltage values: {self.signal[:5]}")
            print(f"First few time values: {self.time[:5]}")
            return True
            
        except Exception as e:
            print(f"Error loading data: {e}")
            self.signal = None
            self.time = None
            return False

    def run(self):
        """Process and emit waveform data with proper coupling"""
        print("Starting waveform projection...")
        
        if self.signal is None or not self.running:
            print("No data available or not running")
            return
            
        try:
            # Create data batch
            data_batch = [[] for _ in range(self.channels)]
            
            # Process voltage data with coupling for channel 1
            if self.coupling_modes[0] == 'AC':
                # Calculate DC offset from entire signal
                dc_offset = np.mean(self.signal)
                processed_signal = self.signal - dc_offset
                print(f"AC Coupling: Removed DC offset of {dc_offset:.3f}V")
                
            elif self.coupling_modes[0] == 'GND':
                # Ground coupling: set entire signal to zero
                processed_signal = np.zeros_like(self.signal)
                print("GND Coupling: Signal grounded")
                
            else:  # DC coupling
                # Pass through original signal
                processed_signal = self.signal
                print("DC Coupling: Original signal preserved")
                
            # Store processed signal in channel 1
            data_batch[0] = processed_signal.tolist()
            
            # Emit the processed data
            print(f"Emitting {len(data_batch[0])} points")
            self.data_received.emit(data_batch)
            
        except Exception as e:
            print(f"Error in run(): {e}")
        finally:
            self.running = False
            print("Waveform processing complete")

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

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Add zoom control buttons
        zoom_layout = QHBoxLayout()
        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_out_btn = QPushButton("Zoom Out")
        self.reset_zoom_btn = QPushButton("Reset Zoom")

        # Style the buttons
        for btn in [self.zoom_in_btn, self.zoom_out_btn, self.reset_zoom_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #293548;
                    color: white;
                    padding: 5px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #3b4d61;
                }
            """)

        # Connect button signals
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)

        # Add buttons to layout
        zoom_layout.addWidget(self.zoom_in_btn)
        zoom_layout.addWidget(self.zoom_out_btn)
        zoom_layout.addWidget(self.reset_zoom_btn)
        layout.addLayout(zoom_layout)

        # Create plot widget with mouse interaction enabled
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#000A1E')
        layout.addWidget(self.plot_widget)

        # Enable mouse interactions
        self.plot_widget.setMouseEnabled(x=True, y=True)
        self.plot_widget.setInteractive(True)

        # Get the ViewBox and enable its features
        self.view_box = self.plot_widget.getViewBox()
        self.view_box.enableAutoRange(axis='xy')
        self.view_box.setMouseMode(self.view_box.RectMode)
        self.view_box.setMenuEnabled(True)

        # Configure plot appearance
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Voltage', 'V')
        self.plot_widget.setLabel('bottom', 'Time', 'ms')
        self.plot_widget.setTitle("Oscilloscope Signal")

        # Create plot curves with different colors
        colors = ['#FF0000', '#00FF00', '#33CCFF', '#FFFF00']
        self.traces = [self.plot_widget.plot([], [], pen=pg.mkPen(color=color, width=2)) 
                      for color in colors]
        
        print("Grid constructed successfully")
        
        # Add trigger indicator attribute
        self.trigger_line = None
        
    def add_trigger_indicator(self, level, color='#FF0000'):
        """Add or update horizontal line indicating trigger level"""
        try:
            # Remove existing trigger line if it exists
            if self.trigger_line is not None:
                self.plot_widget.removeItem(self.trigger_line)
                
            # Create new trigger line
            self.trigger_line = pg.InfiniteLine(
                pos=level, 
                angle=0, 
                pen=pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine),
                movable=False
            )
            self.plot_widget.addItem(self.trigger_line)
            
        except Exception as e:
            print(f"Error adding trigger indicator: {str(e)}")
        
    def zoom_in(self):
        """Zoom in by scaling the view."""
        self.view_box.scaleBy((0.5, 0.5))

    def zoom_out(self):
        """Zoom out by scaling the view."""
        self.view_box.scaleBy((2, 2))

    def reset_zoom(self):
        """Reset the zoom to the default view."""
        self.view_box.autoRange()

    def update_plot(self, data_buffer, channel_active, time_div, voltage_div, 
                    display_window, sample_rate, channel_positions, horizontal_position, 
                    probe_attenuation):
        try:
            for i, trace in enumerate(self.traces):
                if channel_active[i] and data_buffer[i]:
                    # Get raw values for both X and Y
                    y_values = np.array(data_buffer[i], dtype=np.float32)  # Get raw values
                    num_points = len(y_values)  # Define num_points here
                    x_values = np.arange(num_points, dtype=np.float32)  # Get raw values

                    # Apply scaling in the same pattern for both
                    # Y-values scaling
                    y_values = y_values / probe_attenuation  # Apply attenuation
                    y_values = y_values / voltage_div  # Convert to divisions
                    y_values = y_values + channel_positions[i]  # Add position offset

                    # X-values scaling (matching Y pattern)
                    x_values = x_values / num_points  # Normalize
                    x_values = x_values * 8 - 4  # Convert to divisions
                    x_values = x_values * time_div  # Scale by time/div
                    x_values = x_values + horizontal_position * time_div  # Add position offset

                    # Update the trace
                    trace.setData(x_values, y_values)
                    
                    # Both X and Y range calculations using the same simplified style
                    x_range = 4 * time_div
                    self.plot_widget.setXRange(-x_range, x_range)

                    y_range = 4 * voltage_div
                    self.plot_widget.setYRange(-y_range, y_range)
                    
                    # Update grid scales
                    self.plot_widget.getAxis('bottom').setScale(time_div)
                    self.plot_widget.getAxis('left').setScale(voltage_div)

        except Exception as e:
            print(f"Error updating plot: {str(e)}")


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
        self.plot_updated = False
        self.probe_attenuation = 1.0
        self.impedance = 1e6
        self.initUI()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)

        # Add trigger system attributes
        self.trigger_state = "Armed"
        self.pre_trigger_buffer = []
        self.trigger_hysteresis = 0.1  # 10% of vertical division
        self.trigger_position = 0.5  # Default trigger position (center of screen)
        self.last_trigger_index = None
        self.last_trigger_time = 0  # Add this line for holdoff tracking

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
            QSlider::add-page:horizontal {
                background: #475569;
            }
            QSlider::sub-page:horizontal {
                background: #3b82f6;
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

        # FFT Analysis tab setup
        self.setup_fft_tab()
        
        # Connect tab change signal to update FFT when tab is selected
        self.tabs.currentChanged.connect(self.on_tab_changed)

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
        self.main_layout.addWidget(horizontal_group)
          # Changed to self.main_layout


        # Trigger Controls
        trigger_group = QGroupBox("Trigger Controls")
        trigger_layout = QFormLayout()
        
        self.trigger_spinbox = QDoubleSpinBox()
        self.trigger_spinbox.setRange(-5000, 5000)
        self.trigger_spinbox.setValue(0)
        self.trigger_spinbox.valueChanged.connect(self.update_trigger)
        trigger_layout.addRow("Trigger Level (mV):", self.trigger_spinbox)
        
        self.trigger_mode_combo = QComboBox()
        self.trigger_mode_combo.addItems(["Auto", "Normal", "Single"])
        self.trigger_mode_combo.setCurrentText("Auto")
        self.trigger_mode_combo.currentTextChanged.connect(self.update_trigger)
        trigger_layout.addRow("Mode:", self.trigger_mode_combo)
        
        self.trigger_source_combo = QComboBox()
        self.trigger_source_combo.addItems(["CH1", "CH2", "CH3", "CH4", "External"])
        self.trigger_source_combo.setCurrentText("CH1")
        self.trigger_source_combo.currentTextChanged.connect(self.update_trigger)
        trigger_layout.addRow("Source:", self.trigger_source_combo)
        
        self.trigger_slope_combo = QComboBox()
        self.trigger_slope_combo.addItems(["Rising", "Falling"])
        self.trigger_slope_combo.setCurrentText("Rising")
        self.trigger_slope_combo.currentTextChanged.connect(self.update_trigger)
        trigger_layout.addRow("Slope:", self.trigger_slope_combo)
        
        # Add trigger position slider
        self.trigger_pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.trigger_pos_slider.setRange(0, 100)
        self.trigger_pos_slider.setValue(50)  # Center position
        self.trigger_pos_slider.valueChanged.connect(self.update_trigger_position)
        self.trigger_pos_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #334155;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white;
                border: 1px solid #60a5fa;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #e2e8f0;
                border-color: #3b82f6;
            }
            QSlider::add-page:horizontal {
                background: #475569;
            }
            QSlider::sub-page:horizontal {
                background: #3b82f6;
            }
        """)
        trigger_layout.addRow("Trigger Position:", self.trigger_pos_slider)
        
        self.trigger_holdoff_spinbox = QDoubleSpinBox()
        self.trigger_holdoff_spinbox.setRange(0, 1000)
        self.trigger_holdoff_spinbox.setValue(0)
        self.trigger_holdoff_spinbox.valueChanged.connect(self.update_trigger)
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

    def setup_fft_tab(self):
        """Set up the FFT Analysis tab with controls and plot"""
        print("Setting up FFT tab")
        # Main layout structure
        fft_controls_layout = QHBoxLayout()
        
        # Left side - Controls
        controls_group = QGroupBox("FFT Controls")
        controls_layout = QFormLayout()
        
        # FFT Size control
        self.fft_size_combo = QComboBox()
        self.fft_size_combo.addItems(["256", "512", "1024", "2048", "4096", "8192"])
        self.fft_size_combo.setCurrentText("1024")  # Default size
        self.fft_size_combo.currentTextChanged.connect(self.update_fft)
        controls_layout.addRow("FFT Size:", self.fft_size_combo)
        
        # Window function control
        self.window_func_combo = QComboBox()
        self.window_func_combo.addItems(["Rectangular", "Hanning", "Hamming", "Blackman", "Flat-top"])
        self.window_func_combo.setCurrentText("Hanning")  # Default window
        self.window_func_combo.currentTextChanged.connect(self.update_fft)
        controls_layout.addRow("Window:", self.window_func_combo)
        
        # Scale control
        self.fft_scale_combo = QComboBox()
        self.fft_scale_combo.addItems(["Linear", "Logarithmic (dB)"])
        self.fft_scale_combo.setCurrentText("Logarithmic (dB)")  # Default
        self.fft_scale_combo.currentTextChanged.connect(self.update_fft)
        controls_layout.addRow("Scale:", self.fft_scale_combo)
        
        # Channel selection
        self.fft_channel_combo = QComboBox()
        self.fft_channel_combo.addItems(["CH1", "CH2", "CH3", "CH4"])
        self.fft_channel_combo.currentIndexChanged.connect(self.update_fft)
        controls_layout.addRow("Source:", self.fft_channel_combo)
        
        # Update button
        self.update_fft_button = QPushButton("Update FFT")
        self.update_fft_button.clicked.connect(self.update_fft)
        controls_layout.addRow(self.update_fft_button)
        
        # Information display
        self.fft_info_label = QLabel("Peak: N/A")
        controls_layout.addRow(self.fft_info_label)
        
        # Add zoom controls
        zoom_layout = QHBoxLayout()
        self.fft_zoom_in_btn = QPushButton("Zoom In")
        self.fft_zoom_out_btn = QPushButton("Zoom Out")
        self.fft_reset_zoom_btn = QPushButton("Reset Zoom")
        
        # Set styling for buttons
        for btn in [self.fft_zoom_in_btn, self.fft_zoom_out_btn, self.fft_reset_zoom_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #e2e8f0;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #334155;
                }
                QPushButton:pressed {
                    background-color: #0f172a;
                }
            """)
        
        # Connect zoom button signals
        self.fft_zoom_in_btn.clicked.connect(self.fft_zoom_in)
        self.fft_zoom_out_btn.clicked.connect(self.fft_zoom_out)
        self.fft_reset_zoom_btn.clicked.connect(self.fft_reset_zoom)
        
        zoom_layout.addWidget(self.fft_zoom_in_btn)
        zoom_layout.addWidget(self.fft_zoom_out_btn)
        zoom_layout.addWidget(self.fft_reset_zoom_btn)
        controls_layout.addRow("Zoom Controls:", zoom_layout)
        
        controls_group.setLayout(controls_layout)
        fft_controls_layout.addWidget(controls_group)
        
        # Right side - FFT Plot
        self.fft_plot_widget = pg.PlotWidget()
        self.fft_plot_widget.setBackground('#000A1E')
        self.fft_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.fft_plot_widget.setLabel('left', 'Magnitude')
        self.fft_plot_widget.setLabel('bottom', 'Frequency', 'Hz')
        self.fft_plot_widget.setTitle("FFT Spectrum Analysis")
        
        # Set minimum size to ensure visibility
        self.fft_plot_widget.setMinimumSize(500, 300)
        
        # Create FFT plot curve
        self.fft_curve = self.fft_plot_widget.plot([], [], pen=pg.mkPen(color="#00FF00", width=2))
        
        # Store viewbox for zoom operations
        self.fft_view_box = self.fft_plot_widget.getViewBox()
        
        # Configure mouse interaction for zooming
        self.fft_plot_widget.setMouseEnabled(x=True, y=True)  # Enable mouse panning
        
        # Add peak markers
        self.fft_peaks = []  # Will store peak markers
        
        fft_controls_layout.addWidget(self.fft_plot_widget, stretch=3)  # Give plot more space
        
        # Add the controls and plot to the main FFT layout
        self.fft_layout.addLayout(fft_controls_layout)
        
        # Add explanation text
        fft_info_text = QLabel(
            "FFT (Fast Fourier Transform) converts a signal from the time domain to the frequency domain, "
            "showing the frequency components present in the signal. This is useful for analyzing "
            "harmonics, noise, and frequency response."
        )
        fft_info_text.setWordWrap(True)
        self.fft_layout.addWidget(fft_info_text)
    
    def fft_zoom_in(self):
        self.fft_view_box.scaleBy((0.5, 0.5))
    
    def fft_zoom_out(self):
        self.fft_view_box.scaleBy((2, 2))
    
    def fft_reset_zoom(self):
        self.fft_view_box.autoRange()

    def on_tab_changed(self, index):
        """Handle tab switching"""
        if index == 1:  # FFT tab
            print("FFT tab selected, updating display")
            # Force FFT update when switching to FFT tab
            self.update_fft()

    def toggle_channel(self, channel_idx, state):
        if channel_idx == 0:  # Only allow Channel 1 to be toggled
            self.channel_active[channel_idx] = bool(state)
            self.update_plot()

    def populate_com_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.com_port_selector.clear()
        self.com_port_selector.addItems(ports if ports else ["No Ports Found"])

    def update_intensity(self, value):
        """Updates the waveform intensity based on slider value."""
        if not self.plot_window:
            return  # Do nothing if the plot window isn't open

        alpha = value / 100.0  # Normalize slider value to 0–1
        for trace in self.plot_window.traces:
            # Adjust alpha (transparency) of each trace
            color = QColor(trace.opts['pen'].color())
            color.setAlphaF(alpha)
            trace.setPen(pg.mkPen(color=color, width=2))
        
        self.update_plot()  # Redraw plot with updated intensity

    def update_plot(self):
        """Checks trigger conditions and updates the plot with valid data."""
        if not self.plot_window:
            print("Plot window not initialized. Skipping update.")
            return

        # Step 1: Get plot and trigger settings
        time_div = self.time_div_spinbox.value()
        voltage_div = self.volt_div_spinbox.value()
        trigger_level = self.trigger_spinbox.value() / 1000
        trigger_source = self.trigger_source_combo.currentIndex()
        trigger_slope = self.trigger_slope_combo.currentText()
        trigger_mode = self.trigger_mode_combo.currentText()

        # Debug: Notify trigger check
        print("Checking trigger conditions...")

        # Step 2: Trigger Handling
        triggered = False
        if trigger_mode != "Auto":  # Skip trigger checks for Auto mode
            if self.data_buffer[trigger_source] and len(self.data_buffer[trigger_source]) >= 2:
                for i in range(max(0, len(self.data_buffer[trigger_source]) - 100),
                            len(self.data_buffer[trigger_source]) - 1):
                    prev_val = self.data_buffer[trigger_source][i]
                    curr_val = self.data_buffer[trigger_source][i + 1]

                    if ((trigger_slope == "Rising" and prev_val < trigger_level <= curr_val) or
                        (trigger_slope == "Falling" and prev_val > trigger_level >= curr_val)):
                        triggered = True
                        print(f"Trigger detected on channel {trigger_source + 1}")
                        break

        # Step 3: Handle trigger modes
        if trigger_mode == "Normal" and not triggered:
            print("No trigger detected. Skipping plot update.")
            return
        elif trigger_mode == "Single" and triggered:
            print("Single trigger detected. Stopping acquisition.")
            self.stop_acquisition()

        # Step 4: Check data buffer validity and update the plot
        if any(self.data_buffer):  # Ensure there's valid data to plot
            print("Starting plot update...")
            print(f"Buffer data sample (channel 1): {self.data_buffer[0][:5]}")

            # Calculate and update measurements for active channels
            for ch_idx, buffer in enumerate(self.data_buffer):
                if self.channel_active[ch_idx] and buffer:
                    # Adjust buffer for probe attenuation
                    adjusted_buffer = [v / self.probe_attenuation for v in buffer]
                    
                    print(f"DEBUG: Buffer length: {len(adjusted_buffer)}")
                    print(f"DEBUG: sample_rate: {self.sample_rate}, display_window: {self.display_window}")
                    
                    # Calculate frequency using both methods
                    freq_zc = self.calculate_frequency(adjusted_buffer)  # Zero-crossing method
                    freq_fft = self.calculate_frequency_fft(adjusted_buffer)  # FFT method
                    
                    # Use the FFT result if available, otherwise fall back to zero-crossing method
                    freq = freq_fft if freq_fft > 0 else freq_zc
                    
                    print(f"DEBUG: Zero-crossing freq: {freq_zc:.2f} Hz, FFT freq: {freq_fft:.2f} Hz")
                    print(f"DEBUG: Final frequency: {freq:.2f} Hz")
                    
                    if freq > 0:
                        self.measure_freq.setText(f"Frequency: {freq:.2f} Hz")
                    else:
                        self.measure_freq.setText("Frequency: N/A")
                    
                    # Calculate RMS voltage
                    if adjusted_buffer:
                        rms = self.calculate_rms(adjusted_buffer)
                        print(f"DEBUG: Calculated RMS: {rms:.3f} V")
                        self.measure_rms.setText(f"RMS Voltage: {rms:.3f} V")
                    else:
                        self.measure_rms.setText("RMS Voltage: N/A")
                    
                    # Only process the first active channel for measurements
                    break

            # Call the plot window's update method
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
            print("Plot update completed successfully.")
            
            # Update FFT display if the FFT tab is active
            if self.tabs.currentIndex() == 1:  # FFT tab
                self.update_fft()
        else:
            print("Data buffer is empty or invalid. Skipping plot update.")

    def calculate_frequency(self, buffer):
        """Calculate frequency using a more robust method that works with DC offset"""
        if len(buffer) < 10:  # Need enough points for reliable calculation
            print("DEBUG: Not enough points for frequency calculation")
            return 0
            
        # Calculate mean of the signal to handle DC offset
        mean_value = sum(buffer) / len(buffer)
        print(f"DEBUG: Signal mean value: {mean_value}")
        
        # Normalize signal by removing DC offset
        normalized_buffer = [val - mean_value for val in buffer]
        
        # Count zero crossings in the normalized buffer
        crossings = 0
        for i in range(1, min(len(normalized_buffer), self.display_window)):
            if (normalized_buffer[i-1] < 0 and normalized_buffer[i] >= 0) or \
               (normalized_buffer[i-1] > 0 and normalized_buffer[i] <= 0):
                crossings += 1
        
        print(f"DEBUG: Zero crossings detected: {crossings}")
                
        # Use a reasonable default if sample_rate is too small or invalid
        effective_sample_rate = max(100, self.sample_rate)
        
        # Calculate time duration of the displayed signal in seconds
        # Ensure we're using the actual buffer length, not the display window setting
        actual_time_duration = len(buffer) / effective_sample_rate
        print(f"DEBUG: Time duration: {actual_time_duration}s with sample rate {effective_sample_rate}")
        
        # Each complete cycle has 2 zero crossings
        if crossings > 1:
            freq = (crossings / 2) / actual_time_duration
            print(f"DEBUG: Calculated frequency with formula (crossings/2)/time_duration = {freq} Hz")
            return freq
        else:
            print("DEBUG: Not enough crossings for frequency calculation")
            return 0

    def calculate_frequency_fft(self, buffer):
        """Calculate frequency using FFT for more reliable results"""
        if len(buffer) < 20:  # Need enough points for reliable calculation
            return 0
            
        try:
            # Use numpy's FFT for more reliable frequency detection
            # First, convert buffer to numpy array if it's not already
            signal = np.array(buffer)
            
            # Apply Hanning window to reduce spectral leakage
            signal = signal * np.hanning(len(signal))
            
            # Compute FFT and get the magnitude spectrum
            fft_result = np.abs(np.fft.rfft(signal))
            
            # Use a reasonable default if sample_rate is too small or invalid
            effective_sample_rate = max(100, self.sample_rate)
            
            # Compute frequency bins
            freq_bins = np.fft.rfftfreq(len(signal), d=1.0/effective_sample_rate)
            
            # Find the peak frequency (excluding DC component)
            if len(freq_bins) > 1:
                # Skip the first bin (DC component) by starting at index 1
                peak_idx = np.argmax(fft_result[1:]) + 1
                peak_freq = freq_bins[peak_idx]
                
                # Only return frequency if the peak is significant
                if fft_result[peak_idx] > 0.1 * np.max(fft_result):
                    return peak_freq
            
            return 0
        except Exception as e:
            print(f"ERROR in FFT frequency calculation: {str(e)}")
            return 0

    def calculate_rms(self, buffer):
        """Calculate RMS voltage"""
        if not buffer:
            return 0
        
        # Calculate RMS
        rms = np.sqrt(sum([v**2 for v in buffer]) / len(buffer))
        return rms

    def start_acquisition(self):
        """Start data acquisition and initialize SerialReader if necessary."""
        # Step 1: Check if SerialReader already exists
        if not hasattr(self, 'serial_thread') or self.serial_thread is None:
            print("SerialReader instance does not exist. Creating a new instance.")
            self.serial_thread = SerialReader(
                channels=4,
                impedance=self.impedance
            )
            
            # Set initial coupling modes
            for channel, combo in enumerate(self.coupling_combos):
                mode = combo.currentText()
                self.serial_thread.set_channel_coupling(channel, mode)
            
            # Connect the data_received signal to process_data
            self.serial_thread.data_received.connect(self.process_data)

        # Step 2: Debug: Confirm SerialReader instance and its state
        print(f"SerialReader instance ID: {id(self.serial_thread)}")
        print(f"Setting SerialReader.running to True before starting the thread.")

        # Step 3: Start the SerialReader thread
        self.serial_thread.running = True  # Ensure the running flag is set to True
        self.serial_thread.start()

        # Step 4: Start the plot update timer if the plot window exists
        self.is_running = True
        if self.plot_window:
            self.timer.start(50)
            print("Plot update timer started.")

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
        """Process incoming data with trigger handling"""
        try:
            # Get trigger parameters
            trigger_source = self.trigger_source_combo.currentIndex()
            trigger_level = self.trigger_spinbox.value() / 1000
            trigger_mode = self.trigger_mode_combo.currentText()
            trigger_slope = self.trigger_slope_combo.currentText()
            trigger_holdoff = self.trigger_holdoff_spinbox.value() / 1000  # Convert ms to seconds
            
            # Check holdoff period
            current_time = time.time()
            if current_time - self.last_trigger_time < trigger_holdoff:
                return  # Skip processing during holdoff
            
            # Update pre-trigger buffer
            if data[trigger_source] and len(data[trigger_source]) >= 2:
                self.pre_trigger_buffer.extend(data[trigger_source])
                max_pretrigger = int(self.display_window * 2)
                if len(self.pre_trigger_buffer) > max_pretrigger:
                    self.pre_trigger_buffer = self.pre_trigger_buffer[-max_pretrigger:]

            # Check trigger condition
            if self.trigger_state == "Armed" and trigger_mode != "Auto":
                triggered, trigger_idx = self.check_trigger_condition(
                    self.pre_trigger_buffer,
                    trigger_level,
                    trigger_slope
                )

                if triggered:
                    self.trigger_state = "Triggered"
                    self.last_trigger_index = trigger_idx
                    self.last_trigger_time = current_time  # Update last trigger time
                    
                    if trigger_mode == "Single":
                        self.stop_acquisition()

            # Update display data based on trigger position
            trigger_position = self.trigger_pos_slider.value() / 100.0  # Convert to 0-1 range
            
            if self.trigger_state == "Triggered" and self.last_trigger_index is not None:
                start_idx = max(0, self.last_trigger_index - int(self.display_window * trigger_position))
                end_idx = start_idx + self.display_window
                
                display_data = self.pre_trigger_buffer[start_idx:end_idx]
                self.data_buffer[trigger_source] = display_data
            else:
                self.data_buffer = data

            # Update plot
            self.update_plot()
            
            # Force FFT update when new data arrives if FFT tab is visible
            if self.tabs.currentIndex() == 1:  # FFT tab is active
                self.update_fft()
                
        except Exception as e:
            print(f"Error in process_data: {str(e)}")

    def check_trigger_condition(self, data, trigger_level, slope):
        """Check if trigger condition is met"""
        if len(data) < 2:
            return False, None

        # Apply hysteresis
        high_level = trigger_level + (self.volt_div_spinbox.value() * self.trigger_hysteresis)
        low_level = trigger_level - (self.volt_div_spinbox.value() * self.trigger_hysteresis)

        for i in range(1, len(data)):
            prev_val = data[i-1]
            curr_val = data[i]

            if slope == "Rising" and prev_val <= low_level and curr_val >= high_level:
                return True, i
            elif slope == "Falling" and prev_val >= high_level and curr_val <= low_level:
                return True, i

        return False, None

    def update_trigger(self):
        """Handle trigger parameter updates"""
        if not self.is_running:
            return
            
        try:
            # Reset trigger state
            self.trigger_state = "Armed"
            self.last_trigger_index = None
            
            # Clear pre-trigger buffer
            self.pre_trigger_buffer = []
            
            # Update trigger level indicator
            if self.plot_window:
                self.plot_window.add_trigger_indicator(self.trigger_spinbox.value() / 1000)
            
            # Force plot update
            self.update_plot()
            
        except Exception as e:
            print(f"Error updating trigger: {str(e)}")

    def update_trigger_position(self, value):
        """Update trigger position and redraw waveform"""
        try:
            self.trigger_position = value / 100.0  # Convert slider value to 0-1 range
            
            # Update trigger indicator position if plot window exists
            if self.plot_window and hasattr(self, 'pre_trigger_buffer') and self.last_trigger_index is not None:
                # Calculate new display window based on trigger position
                start_idx = max(0, self.last_trigger_index - int(self.display_window * self.trigger_position))
                end_idx = start_idx + self.display_window
                
                if len(self.pre_trigger_buffer) > 0:
                    # Update display data
                    display_data = self.pre_trigger_buffer[start_idx:min(end_idx, len(self.pre_trigger_buffer))]
                    self.data_buffer[self.trigger_source_combo.currentIndex()] = display_data
                    
                    # Force plot update
                    self.update_plot()
                    
        except Exception as e:
            print(f"Error updating trigger position: {str(e)}")

    def change_time_division(self, delta):
        new_val = self.time_div_spinbox.value() + delta
        if 0.1 <= new_val <= self.time_div_spinbox.maximum():  # Same style as voltage division
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

    def update_data(self):
        # We don't need to apply probe attenuation here
        # The attenuation is applied during plotting in PlotWindow.update_plot
        pass


    def update_impedance(self, index):
        impedance_str = self.impedance_combo.currentText()
        old_impedance = self.impedance  # Store previous impedance for scaling
        
        if impedance_str == "1 MΩ":
            self.impedance = 1e6
        elif impedance_str == "50 Ω":
            self.impedance = 50.0

        if self.serial_thread:
            self.serial_thread.set_impedance(self.impedance)

        # Apply impedance effect to data buffer
        # Assuming a source impedance of 600 ohms (typical for audio signals)
        source_impedance = 600.0
        
        # Calculate voltage division factors for old and new impedance
        old_factor = old_impedance / (old_impedance + source_impedance)
        new_factor = self.impedance / (self.impedance + source_impedance)
        
        # Scale factor to adjust the voltage
        if old_factor > 0:  # Avoid division by zero
            scale_factor = new_factor / old_factor
            
            # Apply scaling to all active channels
            for i in range(len(self.data_buffer)):
                if self.channel_active[i] and self.data_buffer[i]:
                    self.data_buffer[i] = [value * scale_factor for value in self.data_buffer[i]]
        
        # Update plot with the new scaled data
        self.update_plot()

    def update_probe_attenuation(self, index):
        attenuation_str = self.probe_attenuation_combo.currentText()
        if attenuation_str == "1x":
            self.probe_attenuation = 1.0
        elif attenuation_str == "10x":
            self.probe_attenuation = 10.0

        # No need to modify data, just update the plot
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

    def toggle_grid(self, state):
        if self.plot_window:
            self.plot_window.plot_widget.showGrid(x=state, y=state, alpha=0.3)

    def update_channel_coupling(self, channel, mode):
        """Update channel coupling mode"""
        if channel < len(self.coupling_combos):
            self.coupling_combos[channel].setCurrentText(mode)
            if self.serial_thread:
                self.serial_thread.set_channel_coupling(channel, mode)

    def update_fft(self):
        """Update the FFT display based on current settings and data"""
        print("Updating FFT display...")
        channel_idx = self.fft_channel_combo.currentIndex()
        
        # Check if selected channel has data
        if not self.channel_active[channel_idx] or not self.data_buffer[channel_idx]:
            print(f"No data for channel {channel_idx+1}")
            self.fft_curve.setData([], [])
            self.fft_info_label.setText("Peak: N/A")
            # Clear any peak markers
            for peak in self.fft_peaks:
                self.fft_plot_widget.removeItem(peak)
            self.fft_peaks = []
            return
        
        try:
            # Get the raw signal data with probe attenuation applied
            signal = np.array(self.data_buffer[channel_idx]) / self.probe_attenuation
            print(f"Processing FFT for channel {channel_idx+1}, buffer length: {len(signal)}")
            
            # Get FFT size
            fft_size = int(self.fft_size_combo.currentText())
            
            # If signal is shorter than FFT size, pad with zeros
            if len(signal) < fft_size:
                signal = np.pad(signal, (0, fft_size - len(signal)), 'constant')
            
            # If signal is longer than FFT size, truncate
            if len(signal) > fft_size:
                signal = signal[:fft_size]
            
            # Apply selected window function
            window_type = self.window_func_combo.currentText().lower()
            if window_type == "rectangular":
                windowed_signal = signal
            elif window_type == "hanning":
                windowed_signal = signal * np.hanning(len(signal))
            elif window_type == "hamming":
                windowed_signal = signal * np.hamming(len(signal))
            elif window_type == "blackman":
                windowed_signal = signal * np.blackman(len(signal))
            elif window_type == "flat-top":
                windowed_signal = signal * np.ones(len(signal))  # Simplified flat-top
            else:
                windowed_signal = signal * np.hanning(len(signal))  # Default to Hanning
            
            # Compute FFT and magnitude
            fft_result = np.fft.rfft(windowed_signal)
            magnitude = np.abs(fft_result)
            
            # Convert to dB if logarithmic scale is selected
            if self.fft_scale_combo.currentText() == "Logarithmic (dB)":
                # Avoid log of zero by adding small value
                magnitude = 20 * np.log10(magnitude + 1e-10)
                y_label = "Magnitude (dB)"
            else:
                y_label = "Magnitude"
            
            # Set Y-axis label based on scale
            self.fft_plot_widget.setLabel('left', y_label)
            
            # Calculate frequency bins
            effective_sample_rate = max(100, self.sample_rate)
            freq_bins = np.fft.rfftfreq(len(signal), d=1.0/effective_sample_rate)
            
            # Update the plot
            print(f"Plotting FFT with {len(freq_bins)} frequency bins")
            self.fft_curve.setData(freq_bins, magnitude)
            
            # Find and mark peaks
            peak_indices = self.find_peaks(magnitude)
            
            # Clear previous peak markers
            for peak in self.fft_peaks:
                self.fft_plot_widget.removeItem(peak)
            self.fft_peaks = []

            # Add new peak markers and update peak info
            if len(peak_indices) > 0:
                # Get the highest peak
                main_peak_idx = peak_indices[0]
                peak_freq = freq_bins[main_peak_idx]
                peak_mag = magnitude[main_peak_idx]
                
                # Create marker for the peak
                peak_marker = pg.ScatterPlotItem()
                peak_marker.addPoints([{
                    'pos': (peak_freq, peak_mag),
                    'size': 10,
                    'pen': {'color': 'red', 'width': 2},
                    'brush': pg.mkBrush('r')
                }])
                self.fft_plot_widget.addItem(peak_marker)
                self.fft_peaks.append(peak_marker)
                
                # Add text label for the peak
                peak_text = pg.TextItem(text=f"{peak_freq:.1f} Hz", color=(255, 0, 0))
                peak_text.setPos(peak_freq, peak_mag)
                self.fft_plot_widget.addItem(peak_text)
                self.fft_peaks.append(peak_text)
                
                # Update info label with frequency and magnitude
                self.fft_info_label.setText(f"Peak: {peak_freq:.1f} Hz @ {peak_mag:.1f}")
            else:
                self.fft_info_label.setText("Peak: N/A")
                
        except Exception as e:
            print(f"Error updating FFT: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def find_peaks(self, magnitude, num_peaks=3, min_height=None):
        """Find peaks in FFT magnitude data with improved detection"""
        try:
            # Skip first few bins to avoid DC component
            start_idx = 3
            if len(magnitude) <= start_idx:
                return []
            
            # If min_height not specified, use a percentage of max magnitude
            if min_height is None:
                min_height = np.max(magnitude[start_idx:]) * 0.1  # 10% of max
            
            # Find peaks
            peaks = []
            for i in range(start_idx + 1, len(magnitude) - 1):
                if (magnitude[i] > magnitude[i-1] and 
                    magnitude[i] > magnitude[i+1] and 
                    magnitude[i] > min_height):
                    peaks.append((i, magnitude[i]))
            
            # Sort peaks by magnitude
            peaks.sort(key=lambda x: x[1], reverse=True)
            
            # Return indices of top peaks
            return [idx for idx, _ in peaks[:num_peaks]]
            
        except Exception as e:
            print(f"Error in find_peaks: {str(e)}")
            return []

    def zoom_in(self):
        """Zoom in by scaling the view."""
        if hasattr(self, 'plot_window') and self.plot_window:
            # Call the PlotWindow's zoom_in method instead of accessing ViewBox directly
            self.plot_window.zoom_in()
            print("Main oscilloscope zoomed in")

    def zoom_out(self):
        """Zoom out by scaling the view."""
        if hasattr(self, 'plot_window') and self.plot_window:
            # Call the PlotWindow's zoom_out method instead of accessing ViewBox directly
            self.plot_window.zoom_out()
            print("Main oscilloscope zoomed out")

    def reset_zoom(self):
        """Reset the zoom to the default view."""
        if hasattr(self, 'plot_window') and self.plot_window:
            # Call the PlotWindow's reset_zoom method instead of accessing ViewBox directly
            self.plot_window.reset_zoom()
            print("Main oscilloscope zoom reset")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = OscilloscopeApp()
    window.show()
    sys.exit(app.exec())