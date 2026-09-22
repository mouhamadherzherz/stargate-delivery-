# -*- coding: utf-8 -*-
"""
Stargate Enterprise ERP V2 - Core Package Initialization
"""

from flask import Flask

def create_app():
    app = Flask(__name__)
    return app
