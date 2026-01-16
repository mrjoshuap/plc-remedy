"""Web dashboard routes."""
from flask import Blueprint, render_template

web = Blueprint('web', __name__)


@web.route('/')
def dashboard():
    """Serve the main dashboard page."""
    return render_template('dashboard.html')
