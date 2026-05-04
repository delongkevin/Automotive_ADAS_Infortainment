"""
Main Application Entry Point

Command-line interface for running ADAS SIL simulations.

Copyright Magna Electronics. All rights reserved.
"""

import argparse
import logging
import json
import sys
from pathlib import Path

from simulator import ADASSILSimulator
from visualization import BirdEyeView, UnityBridge

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('adas_sil.log')
    ]
)

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_path}, using defaults")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        sys.exit(1)


def load_scenario(scenario_path: str) -> dict:
    """
    Load scenario from JSON file.

    Args:
        scenario_path: Path to scenario file

    Returns:
        Scenario dictionary
    """
    try:
        with open(scenario_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Scenario file not found: {scenario_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in scenario file: {e}")
        sys.exit(1)


def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(
        description='ADAS SIL System - Software-in-the-Loop ADAS Simulator'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config/default_config.json',
        help='Path to configuration file'
    )

    parser.add_argument(
        '--scenario',
        type=str,
        required=True,
        help='Path to scenario file or scenario name (e.g., highway_cruise)'
    )

    parser.add_argument(
        '--duration',
        type=float,
        default=60.0,
        help='Simulation duration in seconds (default: 60)'
    )

    parser.add_argument(
        '--viz-2d',
        action='store_true',
        help='Enable 2D bird\'s eye view visualization'
    )

    parser.add_argument(
        '--unity-bridge',
        action='store_true',
        help='Enable Unity/Unreal bridge server'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=5555,
        help='Unity bridge port (default: 5555)'
    )

    parser.add_argument(
        '--real-time',
        action='store_true',
        help='Run simulation at real-time speed'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output file path for simulation results (JSON)'
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ADAS SIL System - Magna Electronics")
    logger.info("=" * 60)

    # Load configuration
    config = load_config(args.config)

    # Load scenario
    scenario_path = args.scenario
    if not scenario_path.endswith('.json'):
        # Try to find scenario by name
        scenario_dir = Path(__file__).parent / 'scenarios'
        scenario_path = scenario_dir / f"{args.scenario}.json"

    scenario = load_scenario(str(scenario_path))

    # Initialize simulator
    logger.info("Initializing simulator...")
    simulator = ADASSILSimulator(config)

    # Load scenario
    simulator.load_scenario(scenario)

    # Initialize visualizations
    viz_2d = None
    unity_bridge = None

    if args.viz_2d:
        logger.info("Initializing 2D visualization...")
        viz_2d = BirdEyeView()
        viz_2d.show()

    if args.unity_bridge:
        logger.info(f"Starting Unity bridge on port {args.port}...")
        unity_bridge = UnityBridge(port=args.port)
        unity_bridge.start()

    # Run simulation
    try:
        logger.info(f"Running simulation for {args.duration}s...")

        # If visualization enabled, run with updates
        if viz_2d or unity_bridge:
            steps = int(args.duration / simulator.dt)
            update_interval = 10  # Update viz every 10 steps

            for i in range(steps):
                simulator.step()

                # Update visualizations periodically
                if i % update_interval == 0:
                    state = simulator.get_state()

                    if viz_2d:
                        viz_2d.update(state)

                    if unity_bridge:
                        unity_bridge.send_state(state)

            logger.info("Simulation completed")
        else:
            # Run without visualization
            results = simulator.run(duration=args.duration, real_time=args.real_time)

        # Get and save results
        results = simulator.get_results()

        logger.info("=" * 60)
        logger.info("Simulation Results")
        logger.info("=" * 60)
        logger.info(f"Duration: {results['duration']:.2f}s")
        logger.info(f"Steps: {results['steps']}")
        logger.info(f"ADAS Events: {len(results['adas_events'])}")

        for event in results['adas_events']:
            logger.info(f"  [{event['time']:.1f}s] {event['feature']}: {event['event']}")

        # Save results to file if specified
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Remove log_data from results (too large)
            results_copy = results.copy()
            del results_copy['log_data']

            with open(output_path, 'w') as f:
                json.dump(results_copy, f, indent=2)

            logger.info(f"Results saved to: {output_path}")

    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user")
        simulator.stop()

    except Exception as e:
        logger.error(f"Simulation error: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # Cleanup
        if viz_2d:
            viz_2d.close()

        if unity_bridge:
            unity_bridge.stop()

    logger.info("ADAS SIL System terminated")


if __name__ == '__main__':
    main()
