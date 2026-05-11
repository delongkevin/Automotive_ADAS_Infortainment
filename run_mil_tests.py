#!/usr/bin/env python
"""
MIL Test Suite Runner - Executes all Model-in-the-Loop tests

This script runs the complete ADAS MIL test suite including:
- Blind spot detection scenarios
- Autonomous parking scenarios (parallel and perpendicular)
- Trailer assistance scenarios
- Surround view camera scenarios
- Performance metrics collection
- Comprehensive reporting

Usage:
    python run_mil_tests.py [--output REPORT_PATH] [--scenario SCENARIO_NAME]
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ADAS_SIL_System import ADASSILSimulator
from ADAS_SIL_System.core.mil_testing import run_mil_test_suite, MILScenarioRunner


def main():
    parser = argparse.ArgumentParser(
        description='Run ADAS MIL Test Suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Run all MIL tests
  python run_mil_tests.py
  
  # Run specific scenario
  python run_mil_tests.py --scenario blind_spot_detection
  
  # Generate report to file
  python run_mil_tests.py --output mil_test_report.txt
  
  # Run with verbose output
  python run_mil_tests.py --verbose
        '''
    )
    
    parser.add_argument(
        '--scenario',
        type=str,
        help='Run specific scenario (without .json extension)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='mil_test_report.txt',
        help='Output path for test report (default: mil_test_report.txt)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Initialize simulator with all ADAS features
    config = {
        'dt': 0.01,
        'adas': {
            'ldw': {'enabled': True},
            'acc': {'enabled': True},
            'aeb': {'enabled': True},
            'bsd': {'enabled': True},
            'parking': {'enabled': True},
            'trailer_assistance': {'enabled': True},
            'trailer_reverse': {'enabled': True},
            'surround_view': {'enabled': True}
        }
    }
    
    print("Initializing ADAS SIL Simulator for MIL Testing...")
    simulator = ADASSILSimulator(config)
    
    scenarios_dir = Path(__file__).parent / 'ADAS_SIL_System' / 'scenarios'
    
    if args.scenario:
        # Run specific scenario
        scenario_path = scenarios_dir / f"{args.scenario}.json"
        
        if not scenario_path.exists():
            print(f"Error: Scenario '{args.scenario}' not found at {scenario_path}")
            return 1
        
        print(f"\nRunning scenario: {args.scenario}")
        runner = MILScenarioRunner(simulator)
        results = runner.run_scenario(str(scenario_path))
        
        # Generate report
        report = runner.generate_report(args.output if args.scenario else None)
        print(report)
    else:
        # Run all test scenarios
        results_data = run_mil_test_suite(simulator, str(scenarios_dir))
        runner = results_data['runner']
        
        # Generate report file
        runner.generate_report(args.output)
        
        # Print exit code based on results
        passed_count = sum(1 for r in runner.results_list if r.overall_pass)
        total_count = len(runner.results_list)
        
        if passed_count == total_count:
            print(f"\n{'='*70}")
            print(f"ALL MIL TESTS PASSED ({passed_count}/{total_count})")
            print(f"{'='*70}\n")
            return 0
        else:
            print(f"\n{'='*70}")
            print(f"SOME MIL TESTS FAILED ({passed_count}/{total_count} passed)")
            print(f"{'='*70}\n")
            return 1


if __name__ == '__main__':
    sys.exit(main())
