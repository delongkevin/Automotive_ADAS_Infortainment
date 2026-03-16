import sys
import pickle
import time

import serial
from serial.tools import list_ports
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel,
    QComboBox, QLineEdit, QHBoxLayout, QGridLayout
)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QCoreApplication, QSettings, QTimer, QThread, Signal


class NetBooterControl(QWidget):

    def __init__(self):
        super().__init__()
        self.settings_file = "settings.pkl"
        self.load_settings()
        self.connected = False
        self.serial_connection = None
        self.power_supply_connected = False
        self.power_supply_serial_connection = None
        self.initUI()
        self.ps_update_thread = PowerSupplyUpdateThread(self)
        self.ps_update_thread.update_signal.connect(self.update_power_supply_labels)
        self.ps_update_thread.disconnected_signal.connect(self.handle_ps_disconnection)

    def initUI(self):
        main_layout, sections_layout = QVBoxLayout(), QHBoxLayout()
        self.init_netbooter_section(sections_layout)
        self.init_power_supply_section(sections_layout)
        main_layout.addLayout(sections_layout)
        self.init_status_banner(main_layout)
        self.setLayout(main_layout)
        self.setWindowTitle('NetBooter Control')
        self.setWindowIcon(QIcon("outlet_icon.ico"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()

    def init_netbooter_section(self, sections_layout):
        netbooter_layout = QVBoxLayout()
        self.com_port_label, self.com_port_combo = self.create_label_combo("Power Outlets:", self.get_available_ports())
        self.connect_button, self.disconnect_button = self.create_connection_buttons(self.connect_to_device, self.disconnect_from_device)
        self.outlet_buttons, self.outlet_name_edits = self.create_outlets()
        netbooter_layout.addWidget(self.com_port_label)
        netbooter_layout.addWidget(self.com_port_combo)
        netbooter_layout.addLayout(self.create_horizontal_layout([self.connect_button, self.disconnect_button]))
        netbooter_layout.addLayout(self.create_grid_layout(self.outlet_name_edits, self.outlet_buttons))
        sections_layout.addLayout(netbooter_layout)

    def init_power_supply_section(self, sections_layout):
        self.ps_layout = QVBoxLayout()
        self.ps_com_port_label, self.ps_com_port_combo = self.create_label_combo("Power Supply:", self.get_available_ports())
        self.ps_connect_button, self.ps_disconnect_button = self.create_connection_buttons(self.connect_to_power_supply, self.disconnect_from_power_supply)
        self.voltage_label, self.current_label = QLabel("Voltage: --.--"), QLabel("Current: ---.---")
        self.output_on_button, self.output_off_button = QPushButton("On"), QPushButton("Off")
        self.output_on_button.clicked.connect(self.turn_on_power_supply)
        self.output_off_button.clicked.connect(self.turn_off_power_supply)

        self.ps_layout.addWidget(self.ps_com_port_label)
        self.ps_layout.addWidget(self.ps_com_port_combo)
        self.ps_layout.addLayout(self.create_horizontal_layout([self.ps_connect_button, self.ps_disconnect_button]))
        self.ps_layout.addLayout(self.create_horizontal_layout([self.voltage_label, self.output_on_button]))
        self.ps_layout.addLayout(self.create_horizontal_layout([self.current_label, self.output_off_button]))
        sections_layout.addLayout(self.ps_layout)

    def turn_on_power_supply(self):
        response = self.send_ps_command("OUT1")
        if response is None:
            self.update_status("Failed to turn on the power supply!", "red")

    def turn_off_power_supply(self):
        response = self.send_ps_command("OUT0")
        if response is None:
            self.update_status("Failed to turn off the power supply!", "red")

    def init_status_banner(self, main_layout):
        self.status_banner = QLabel("Ready")
        self.status_banner.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_banner)

    def create_label_combo(self, label_text, items):
        label, combo = QLabel(label_text), QComboBox()
        combo.addItems(items)
        return label, combo

    def create_connection_buttons(self, connect_func, disconnect_func):
        connect_button, disconnect_button = QPushButton("Connect"), QPushButton("Disconnect")
        connect_button.clicked.connect(connect_func)
        disconnect_button.clicked.connect(disconnect_func)
        return connect_button, disconnect_button

    def create_outlets(self):
        outlet_buttons, outlet_name_edits = [], []
        for i in range(2):
            outlet_name_edit = QLineEdit(self.outlet_names[i])
            outlet_name_edits.append(outlet_name_edit)
            button = self.create_toggle_button(i)
            outlet_buttons.append(button)
        return outlet_buttons, outlet_name_edits

    def create_toggle_button(self, outlet_index):
        button = QPushButton("Off")
        button.setCheckable(True)
        button.clicked.connect(lambda: self.toggle_outlet(outlet_index))
        button.setStyleSheet(self.get_button_stylesheet(False))
        return button

    def create_horizontal_layout(self, widgets):
        layout = QHBoxLayout()
        for widget in widgets:
            layout.addWidget(widget)
        return layout

    def create_grid_layout(self, name_edits, buttons):
        layout = QGridLayout()
        for i, (name_edit, button) in enumerate(zip(name_edits, buttons)):
            layout.addWidget(name_edit, i, 0)
            layout.addWidget(button, i, 1)
        return layout

    def handle_ps_disconnection(self):
        self.power_supply_connected = False
        self.ps_update_thread.stop()
        self.voltage_label.setText("Voltage: --.--")
        self.current_label.setText("Current: ---.---")
        self.update_status("Power supply disconnected!", "red")

    def update_power_supply_labels(self, voltage, current):
        self.voltage_label.setText(f"Voltage: {voltage}")
        self.current_label.setText(f"Current: {current}")

    def connect_to_device(self):
        if self.connected:
            self.update_status("Already connected!", "blue")
            return
        try:
            self.serial_connection = serial.Serial(
                port=self.com_port_combo.currentText().split(" - ")[0],
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            self.connected = True
            self.update_outlet_status_from_device()
        except Exception as e:
            self.update_status(f"Failed to connect to device: {e}", "red")
            self.connected = False
            self.serial_connection = None

    def update_status(self, message, color="black"):
        self.status_banner.setText(message)
        self.status_banner.setStyleSheet(f"color: {color};")

    def disconnect_from_device(self):
        if not self.connected:
            self.update_status("Already disconnected!", "blue")
            return
        try:
            self.serial_connection.close()
            self.connected = False
        except Exception as e:
            self.update_status(f"Failed to disconnect from device: {e}", "red")

    def update_outlet_status_from_device(self):
        try:
            if not self.connected:
                self.update_status("Device is not connected!", "red")
                return
            send = f'$A5\n'
            self.serial_connection.write(send.encode('utf-8'))
            response = self.read_com_output(send)
            if not response:
                raise Exception("No response from device")
            init_retval = response.split(',')[-1]
            outlet_statuses = [int(x) for x in init_retval]
            outlet_statuses.reverse()
            for i, status in enumerate(outlet_statuses):  # Reverse to match the described order
                self.outlet_buttons[i].setChecked(status == 1)
                self.outlet_buttons[i].setText("On" if status else "Off")
                self.outlet_buttons[i].setStyleSheet(self.get_button_stylesheet(status))
        except Exception as e:
            self.update_status(f"Failed to fetch initial status from device: {e}", 'red')
            return

    def get_icon(self, color):
        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.green if color == "green" else Qt.red)
        return QIcon(pixmap)

    def get_available_ports(self):
        ports = list_ports.comports()
        return [f"{port.device} - {port.description}" for port in ports]

    def toggle_outlet(self, outlet_index):
        state = not self.outlet_buttons[outlet_index].isChecked()
        try:
            if not self.connected:
                self.update_status("Device is not connected!", "red")
                return
            send = f'$A3 {outlet_index + 1} {1 if state else 0}\n'
            self.serial_connection.write(send.encode('utf-8'))
            response = self.read_com_output(send)
            if '$A0' not in response:
                raise Exception(f"Return value was not OK: {response}")
            self.outlet_buttons[outlet_index].setText("On" if state else "Off")
            self.outlet_buttons[outlet_index].setStyleSheet(self.get_button_stylesheet(state))
        except Exception as e:
            self.update_status(f"Failed to communicate with device: {e}", 'red')
            self.outlet_buttons[outlet_index].setText("On" if not state else "Off")
            self.outlet_buttons[outlet_index].setStyleSheet(self.get_button_stylesheet(not state))
            return

    def get_button_stylesheet(self, state):
        return f"""
            QPushButton {{
                background-color: {'#90EE90' if state else '#FFC0CB'};
            }}
        """

    def read_com_output(self, sent=None, timeout=5):
        start_time = time.time()
        buffer = ""
        while time.time() - start_time < timeout:
            time.sleep(.01)
            buffer += self.serial_connection.read(self.serial_connection.inWaiting()).decode('utf-8', 'replace').replace('\x00', '')
            if any([x in buffer for x in ['$AF', '$A0']]):
                time.sleep(.3)
                buffer += self.serial_connection.read(self.serial_connection.inWaiting()).decode('utf-8', 'replace').replace('\x00', '')
                print(buffer)
                buffer = buffer.strip().split('\n')[-1]
                self.serial_connection.flushInput()
                self.serial_connection.flushOutput()
                return buffer
        return False

    def load_settings(self):
        try:
            with open(self.settings_file, "rb") as f:
                data = pickle.load(f)
                self.com_port = data.get("com_port", "")
                self.outlet_names = data.get("outlet_names", ["Outlet 1", "Outlet 2"])
                self.power_supply_com_port = data.get("power_supply_com_port", "")

        except (FileNotFoundError, pickle.PickleError):
            self.com_port = ""
            self.outlet_names = ["Outlet 1", "Outlet 2"]

    def closeEvent(self, event):
        # Save settings when closing the app
        settings = {
            "com_port": self.com_port_combo.currentText(),
            "outlet_names": [edit.text() for edit in self.outlet_name_edits],
            "power_supply_com_port": self.ps_com_port_combo.currentText()
        }
        with open(self.settings_file, "wb") as f:
            pickle.dump(settings, f)

    def connect_to_power_supply(self):
        if self.power_supply_connected:
            self.update_status("Already connected!", "blue")
            return
        try:
            self.power_supply_serial_connection = serial.Serial(
                port=self.ps_com_port_combo.currentText().split(" - ")[0],
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            self.power_supply_connected = True
            self.update_power_supply_status()
            if self.power_supply_connected:
                self.ps_update_thread.start()
        except Exception as e:
            self.update_status(f"Failed to connect to power supply: {e}", "red")
            self.power_supply_connected = False
            self.power_supply_serial_connection = None

    def disconnect_from_power_supply(self):
        if not self.power_supply_connected:
            self.update_status("Already disconnected!", "blue")
            return
        try:
            self.power_supply_serial_connection.close()
            self.power_supply_connected = False
            if not self.power_supply_connected:
                self.ps_update_thread.stop()
                self.ps_update_thread.wait()
        except Exception as e:
            self.update_status(f"Failed to disconnect from power supply: {e}", "red")

    def update_power_supply_status(self):
        voltage = self.send_ps_command("VOUT1?")
        current = self.send_ps_command("IOUT1?")
        self.voltage_label.setText(f"Voltage: {voltage}")
        self.current_label.setText(f"Current: {current}")

    def send_ps_command(self, command):
        if not self.power_supply_connected:
            return None
        try:
            self.power_supply_serial_connection.write(command.encode('utf-8'))
            response = self.power_supply_serial_connection.readline().decode('utf-8').strip()
            return response
        except serial.SerialException as e:
            return None
        except Exception as e:
            self.update_status(f"Failed to communicate with power supply: {e}", "red")
            return None


class PowerSupplyUpdateThread(QThread):
    update_signal = Signal(str, str)  # Signal for Voltage and Current
    disconnected_signal = Signal()

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            voltage = self.controller.send_ps_command("VOUT1?")
            current = self.controller.send_ps_command("IOUT1?")
            if voltage and current:
                self.update_signal.emit(voltage, current)
            else:
                self.disconnected_signal.emit()
                break
            self.msleep(500)

    def stop(self):
        self.running = False


QSettings.setDefaultFormat(QSettings.IniFormat)
QCoreApplication.setOrganizationName("NetBooterControlApp")
QCoreApplication.setApplicationName("NetBooter Control")

app = QApplication([])
window = NetBooterControl()
sys.exit(app.exec())
