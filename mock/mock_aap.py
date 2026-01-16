"""Mock Ansible Automation Platform API server for testing."""
from flask import Flask, request, jsonify
import logging
import random
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory job storage
_jobs = {}
_job_counter = 1000


@app.route('/api/v2/job_templates/<int:template_id>/launch/', methods=['POST'])
def launch_job(template_id):
    """Launch a mock job template."""
    global _job_counter
    
    logger.info(f"Received job launch request for template {template_id}")
    
    job_id = _job_counter
    _job_counter += 1
    
    # Create job record
    job = {
        'id': job_id,
        'status': 'pending',
        'job_template': template_id,
        'created': datetime.now().isoformat(),
        'extra_vars': request.json.get('extra_vars', {}) if request.is_json else {}
    }
    
    _jobs[job_id] = job
    
    logger.info(f"Created job {job_id} for template {template_id}, status: pending")
    
    return jsonify({
        'id': job_id,
        'status': 'pending',
        'url': f'/api/v2/jobs/{job_id}/',
        'job_template': template_id
    }), 201


@app.route('/api/v2/jobs/<int:job_id>/', methods=['GET'])
def get_job(job_id):
    """Get job status."""
    logger.info(f"Received job status request for job {job_id}")
    
    if job_id not in _jobs:
        logger.warning(f"Job {job_id} not found")
        return jsonify({'error': 'Job not found'}), 404
    
    job = _jobs[job_id]
    
    # Calculate elapsed time since job creation
    created_time = datetime.fromisoformat(job['created'])
    elapsed_seconds = (datetime.now() - created_time).total_seconds()
    
    # Time-based job progression (deterministic)
    # 0-2 seconds: pending
    # 2-5 seconds: running
    # 5+ seconds: successful (or failed with 5% chance)
    
    old_status = job['status']
    if job['status'] == 'pending':
        if elapsed_seconds >= 2:
            job['status'] = 'running'
            job['started'] = datetime.now().isoformat()
            logger.info(f"Job {job_id} transitioned from pending to running (elapsed: {elapsed_seconds:.1f}s)")
    elif job['status'] == 'running':
        if elapsed_seconds >= 5:
            # 5% chance of failure to simulate real-world scenarios
            if random.random() < 0.05:
                job['status'] = 'failed'
            else:
                job['status'] = 'successful'
            job['finished'] = datetime.now().isoformat()
            logger.info(f"Job {job_id} transitioned from running to {job['status']} (elapsed: {elapsed_seconds:.1f}s)")
    
    # Log status if it changed
    if old_status != job['status']:
        logger.info(f"Job {job_id} status changed: {old_status} -> {job['status']}")
    
    # Calculate elapsed time for response
    if job.get('started'):
        started_time = datetime.fromisoformat(job['started'])
        elapsed = int((datetime.now() - started_time).total_seconds())
    else:
        elapsed = int(elapsed_seconds) if elapsed_seconds > 0 else 0
    
    logger.info(f"Returning job {job_id} status: {job['status']} (elapsed: {elapsed}s)")
    
    return jsonify({
        'id': job_id,
        'status': job['status'],
        'finished': job.get('finished') is not None,
        'failed': job['status'] == 'failed',
        'elapsed': elapsed,
        'job_template': job['job_template']
    })


@app.route('/api/v2/jobs/<int:job_id>/stdout/', methods=['GET'])
def get_job_stdout(job_id):
    """Get job stdout output."""
    logger.info(f"Received stdout request for job {job_id}")
    
    if job_id not in _jobs:
        logger.warning(f"Job {job_id} not found for stdout request")
        return jsonify({'error': 'Job not found'}), 404
    
    job = _jobs[job_id]
    
    output = f"""Mock AAP Job Output (Job ID: {job_id})
========================================
PLAY [Remediation Task] ****************

TASK [Execute remediation action] ******
ok: [localhost]

PLAY RECAP *****************************
localhost                  : ok=1    changed=0    unreachable=0    failed=0
"""
    
    return output, 200, {'Content-Type': 'text/plain'}


if __name__ == '__main__':
    logger.info("Starting Mock AAP API server on http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=True)
