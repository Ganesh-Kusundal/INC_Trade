# Loop Objective: Dhan Connection Error Resilience Optimization

## Goal
Improve error handling, type safety, and connection lifecycle robustness in the Dhan broker adapter during startup and recovery.

## Target Metric
`tests.passed` > 0 and `type_errors` == 0

## Target Files
- brokers/dhan/connection.py
- brokers/dhan/exceptions.py

## Verification Command
pytest brokers/dhan/tests/ -v
