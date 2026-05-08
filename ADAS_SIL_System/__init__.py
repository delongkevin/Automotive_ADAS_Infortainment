"""
ADAS SIL (Software-in-the-Loop) System

A comprehensive standalone ADAS simulation system with 3D visualization capabilities
for testing Advanced Driver Assistance Systems in a software-in-the-loop environment.

Copyright Magna Electronics. All rights reserved.
"""

__version__ = "1.0.0"
__author__ = "Magna Electronics ADAS Team"

from .simulator import ADASSILSimulator

__all__ = ['ADASSILSimulator']
