#!/bin/bash

# Get the PIDs of the running import_articles.sh scripts
PIDS=$(pgrep -f "/home/molonews/molonews/import_articles.sh")

# Check if the PID list is not empty
if [[ ! -z "$PIDS" ]]; then
  # Process each PID
  for PID in $PIDS; do
    # Find the running time of each process in seconds and convert to minutes
    RUNTIME=$(ps -p $PID -o etimes=)
    RUNTIME=$((RUNTIME / 60))

    # If the running time is more than 60 minutes, kill the process
    if [[ $RUNTIME -gt 60 ]]; then
      echo "Killing process $PID running for $RUNTIME minutes."
      kill $PID
    else
      echo "Process $PID is running for $RUNTIME minutes, no action needed."
    fi
  done
else
  echo "No process found."
fi
