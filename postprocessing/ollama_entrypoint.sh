#!/bin/bash

    # Start Ollama server in the background
    ollama serve &

    # Wait for Ollama server to be ready (optional, but good practice)
    sleep 5 

    # Pull the specified model if not already present
    if [ -n "$OLLAMA_MODEL" ]; then
        echo "Checking if model $OLLAMA_MODEL is already available..."
        if ollama list | grep -q "$OLLAMA_MODEL"; then
            echo "Model $OLLAMA_MODEL is already available, skipping download."
        else
            echo "Model $OLLAMA_MODEL not found, downloading..."
            ollama pull "$OLLAMA_MODEL"
        fi
    fi

    # Keep the server running
    wait $!