"""
Core Package Initialization

Exports core simulation components.

Copyright Magna Electronics. All rights reserved.
"""

from .vehicle_dynamics import VehicleDynamics
from .sensors import BaseSensor, RadarSensor, CameraSensor

__all__ = ['VehicleDynamics', 'BaseSensor', 'RadarSensor', 'CameraSensor']
