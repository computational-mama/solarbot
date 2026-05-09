#!/bin/bash
pkill -INT -f "chatbot-ui.py"
sleep 1
pkill -TERM -f "node"
pkill -TERM -f "yarn"
pkill -TERM -f "npm"
