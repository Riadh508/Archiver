#!/usr/bin/env python3
"""Test arch module"""
import sys
sys.path.insert(0, "E:/ho/arch")
from arch.__main__ import main
sys.argv = ["arch", "--help"]
main()
