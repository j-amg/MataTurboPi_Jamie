# common/lib/line_sensors.py
# 4x IR line sensor via I2C (TurboPi typical address 0x77)
# Returns [s0,s1,s2,s3] as booleans.
#
# Robust against intermittent: OSError [Errno 121] Remote I/O error

import time
from typing import List, Optional

try:
    from smbus2 import SMBus
except ImportError as e:
    raise ImportError("Missing smbus2. Install with: sudo apt install -y python3-smbus || pip install smbus2") from e


class LineSensors:
    # NOTE: Hiwonder hardware ships with address 0x78.
    # If sensors read all-False on real hardware, try 0x78 vs 0x77 using scan_i2c_bus().
    def __init__(self, bus_num: int = 1, address: int = 0x78, register: int = 0x01):
        self.bus_num = int(bus_num)
        self.address = int(address)
        self.register = int(register)
        self.bus = SMBus(self.bus_num)

    def close(self):
        try:
            self.bus.close()
        except Exception:
            pass

    def _read_byte(self) -> int:
        return self.bus.read_byte_data(self.address, self.register)

    def read(self, retries: int = 4, retry_delay_s: float = 0.02) -> List[bool]:
        last_err: Optional[Exception] = None
        for _ in range(int(retries)):
            try:
                v = self._read_byte()
                # bit0..bit3
                return [
                    bool(v & 0x01),
                    bool(v & 0x02),
                    bool(v & 0x04),
                    bool(v & 0x08),
                ]
            except OSError as e:
                last_err = e
                time.sleep(float(retry_delay_s))
        raise last_err  # type: ignore
