#!/usr/bin/env python3
"""
infrared_lib.py
Infrared line sensor helper with retries and optional I2C bus scan.
"""
__version__ = "1.1.0"


import time
from typing import List, Optional

from line_sensors import LineSensors


class Infrared:
    # NOTE: Hiwonder hardware ships with address 0x78.
    # If sensors read all-False on real hardware, try scan_i2c_bus() to confirm.
    def __init__(self, bus_num: int = 1, address: int = 0x78, register: int = 0x01):
        self.sensor = LineSensors(bus_num=bus_num, address=address, register=register)
        self.address = int(address)
        self.register = int(register)
        self.bus_num = int(bus_num)

    def close(self) -> None:
        self.sensor.close()

    def read(self, retries: int = 4, retry_delay_s: float = 0.02) -> List[bool]:
        return self.sensor.read(retries=retries, retry_delay_s=retry_delay_s)

    def read_raw(self, retries: int = 4, retry_delay_s: float = 0.02) -> int:
        last_err: Optional[Exception] = None
        for _ in range(int(retries)):
            try:
                return self.sensor._read_byte()  # noqa: SLF001 - controlled internal reuse
            except OSError as e:
                last_err = e
                time.sleep(float(retry_delay_s))
        raise last_err  # type: ignore

    def scan_i2c_bus(self) -> List[str]:
        devices: List[str] = []
        bus = self.sensor.bus
        for addr in range(0x00, 0x80):
            try:
                bus.read_byte(addr)
                devices.append(hex(addr))
            except Exception:
                pass
        return devices


_IR_SINGLETON: Optional[Infrared] = None


def get_infrared(bus_num: int = 1, address: int = 0x78, register: int = 0x01) -> Infrared:
    global _IR_SINGLETON
    if _IR_SINGLETON is None:
        _IR_SINGLETON = Infrared(bus_num=bus_num, address=address, register=register)
    return _IR_SINGLETON

