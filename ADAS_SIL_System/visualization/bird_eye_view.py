"""
2D Bird's Eye View Visualization

Real-time 2D visualization of vehicle, environment, and sensor coverage.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.animation import FuncAnimation
from matplotlib.transforms import Affine2D
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BirdEyeView:
    """
    2D bird's-eye visualization using matplotlib.

    Shows:
    - Ego vehicle and orientation
    - Detected objects
    - Sensor coverage areas
    - Lane markings
    - ADAS status indicators
    """

    def __init__(self, config: Dict = None):
        """
        Initialize visualization.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Visualization parameters
        self.view_range = self.config.get('view_range', 100.0)  # meters
        self.update_interval = self.config.get('update_interval', 50)  # ms

        # Create figure
        self.fig, self.ax = plt.subplots(figsize=(12, 10))
        self.ax.set_aspect('equal')
        self.ax.grid(True, alpha=0.3)
        self.ax.set_xlim(-self.view_range, self.view_range)
        self.ax.set_ylim(-20, self.view_range * 1.2)
        self.ax.set_xlabel('Lateral Position (m)')
        self.ax.set_ylabel('Longitudinal Position (m)')
        self.ax.set_title('ADAS SIL System - Bird\'s Eye View')

        # Plot elements (initialized as None, created in update)
        self.ego_vehicle_patch = None
        self.ego_arrow_patch = None
        self.sensor_patches = []
        self.object_patches = []
        self.lane_lines = []

        # Status text
        self.status_text = self.ax.text(
            0.02, 0.98, '', transform=self.ax.transAxes,
            verticalalignment='top', fontfamily='monospace',
            fontsize=9, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        )

        logger.info("Bird's eye view visualization initialized")

    def update(self, state: Dict):
        """
        Update visualization with current simulation state.

        Args:
            state: Current simulation state dictionary
        """
        # Clear previous elements
        if self.ego_vehicle_patch:
            self.ego_vehicle_patch.remove()
            self.ego_vehicle_patch = None
        if self.ego_arrow_patch:
            self.ego_arrow_patch.remove()
            self.ego_arrow_patch = None

        for patch in self.sensor_patches + self.object_patches:
            patch.remove()
        self.sensor_patches.clear()
        self.object_patches.clear()

        for line in self.lane_lines:
            line.remove()
        self.lane_lines.clear()

        # Draw ego vehicle
        self._draw_ego_vehicle(state['vehicle'])

        # Draw sensor coverage
        self._draw_sensor_coverage(state['vehicle'], state['sensors'])

        # Draw detected objects (placeholder - would come from sensor data)
        # self._draw_objects(state.get('detections', []))

        # Update status text
        self._update_status_text(state)

        # Refresh display
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

    def _draw_ego_vehicle(self, vehicle_state: Dict):
        """
        Draw ego vehicle rectangle.

        Args:
            vehicle_state: Vehicle state dictionary
        """
        pos = vehicle_state['position']
        yaw = vehicle_state['orientation']['yaw']
        dims = vehicle_state['dimensions']

        # Vehicle rectangle in vehicle-local coordinates
        width = dims['width']
        length = dims['length']

        rect = patches.Rectangle(
            (-length/2, -width/2), length, width,
            linewidth=2, edgecolor='blue', facecolor='lightblue', alpha=0.7
        )
        transform = Affine2D().rotate_around(0.0, 0.0, yaw).translate(
            pos['x'], pos['y']
        ) + self.ax.transData
        rect.set_transform(transform)

        # Add direction indicator (arrow)
        arrow_length = length * 0.4
        arrow = patches.FancyArrow(
            -length * 0.1, 0, arrow_length, 0,
            width=width*0.3, head_width=width*0.6, head_length=length*0.2,
            fc='darkblue', ec='darkblue', alpha=0.8
        )
        arrow.set_transform(transform)

        self.ax.add_patch(rect)
        self.ax.add_patch(arrow)

        self.ego_vehicle_patch = rect
        self.ego_arrow_patch = arrow

    def _draw_sensor_coverage(self, vehicle_state: Dict, sensors: Dict):
        """
        Draw sensor field-of-view coverage areas.

        Args:
            vehicle_state: Vehicle state
            sensors: Dictionary of sensor information
        """
        for sensor_id, sensor_info in sensors.items():
            if not sensor_info.get('enabled', True):
                continue

            sensor_pos = sensor_info['position']
            max_range = sensor_info['max_range']
            fov_h = np.deg2rad(sensor_info['fov_horizontal'])

            # Draw FOV wedge
            theta1 = np.rad2deg(-fov_h / 2)
            theta2 = np.rad2deg(fov_h / 2)

            wedge = patches.Wedge(
                (sensor_pos[0], sensor_pos[1]), max_range,
                theta1, theta2,
                alpha=0.15, facecolor='green' if 'radar' in sensor_id else 'yellow',
                edgecolor='green' if 'radar' in sensor_id else 'orange',
                linewidth=1
            )

            self.ax.add_patch(wedge)
            self.sensor_patches.append(wedge)

    def _update_status_text(self, state: Dict):
        """
        Update status text box with current information.

        Args:
            state: Current simulation state
        """
        vehicle = state['vehicle']
        adas = state.get('adas', {})

        speed_kmh = vehicle['velocity']['speed'] * 3.6

        status_lines = [
            f"Time: {state['time']:.1f}s",
            f"Speed: {speed_kmh:.1f} km/h",
            f"Position: ({vehicle['position']['x']:.1f}, {vehicle['position']['y']:.1f})m",
            "",
            "=== ADAS Status ==="
        ]

        # LDW status
        if 'ldw' in adas:
            ldw = adas['ldw']
            status = "ACTIVE" if ldw.get('warning_active') else "OK"
            side = ldw.get('warning_side', '-')
            status_lines.append(f"LDW: {status} ({side})")

        # ACC status
        if 'acc' in adas:
            acc = adas['acc']
            if acc.get('enabled'):
                set_speed = acc.get('set_speed', 0.0) * 3.6
                status = "ACTIVE" if acc.get('active') else "STANDBY"
                status_lines.append(f"ACC: {status} (Set: {set_speed:.0f} km/h)")
            else:
                status_lines.append("ACC: OFF")

        # AEB status
        if 'aeb' in adas:
            aeb = adas['aeb']
            if aeb.get('braking_active'):
                status_lines.append(f"AEB: BRAKING ({aeb.get('braking_level', 0)*100:.0f}%)")
            elif aeb.get('warning_active'):
                status_lines.append("AEB: WARNING")
            else:
                status_lines.append("AEB: READY")

        self.status_text.set_text('\n'.join(status_lines))

    def show(self):
        """Display the visualization window."""
        plt.ion()
        plt.show()

    def close(self):
        """Close the visualization window."""
        plt.close(self.fig)
