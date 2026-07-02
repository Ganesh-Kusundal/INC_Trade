# Autoresearch Objective: Dhan Connection Lifecycle Error Resilience

## Goal
Improve error handling, type safety, and connection lifecycle robustness in the Dhan broker adapter during startup and recovery.

## Target Metric
`tests.passed` should increase or remain 100%, and `type_errors` must be 0.

## Allowed Target Files
- `brokers/dhan/connection.py`
- `brokers/dhan/exceptions.py`
