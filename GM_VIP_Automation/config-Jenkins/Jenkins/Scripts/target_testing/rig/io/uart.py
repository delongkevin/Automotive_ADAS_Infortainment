import datetime
import threading
import serial

from ..config import LOG_FOLDER, logger

class UARTConsole(serial.Serial):
    def __init__(self, com_definition: dict, key: str):
        self.key = key
        logger.debug(f'Initializing UART Console "{key}" on {com_definition["port"]}')
        super().__init__(
            port=com_definition['port'],
            baudrate=com_definition['baudrate'],
            bytesize=com_definition['data'],
            parity=com_definition['parity'],
            stopbits=com_definition['stop'],
            timeout=1,
        )
        self.log_file = LOG_FOLDER / f'{self.key}.log'
        self.log_file.unlink(missing_ok=True)
        self.buffer, self._stop = [], False
        self.lock = threading.Lock()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        with open(self.log_file, 'a', encoding='utf-8', errors='ignore') as f:
            while not self._stop:
                try:
                    raw = self.readline()
                except Exception:
                    continue
                if not raw:
                    continue
                line = raw.decode('utf-8', 'ignore').strip()
                if line:
                    logger.debug(f'UART {self.key}: {line}')
                    f.write(f'{datetime.datetime.now()}: {line}\n')
                    f.flush()
                    with self.lock:
                        self.buffer.append(line)

    def get_data(self):
        with self.lock:
            data = self.buffer.copy()
            self.buffer.clear()
            return data

    def stop(self):
        self._stop = True
        try:
            self.close()
        except Exception:
            pass

    def __del__(self):
        self.stop()
